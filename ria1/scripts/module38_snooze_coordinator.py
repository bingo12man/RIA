"""RIA: LLM-selected, session-bound, replay-safe snoozing."""

import json
import re
import subprocess
import time

from ria1.scripts.module15_agent_bridge import ROOT, PYTHON
from ria1.scripts.module15_tool_executor import OWNER, _ledger_connect
from ria1.scripts.module20_native_sessions import get_history
from ria1.scripts.module23_reminder_discovery import (
    list_pending_reminders,
    validate_selected_reminder,
)
from ria1.scripts.module37_snooze_interpreter import interpret_snooze
from ria1.scripts.module8_command_executor import request_reminders

TTL = 300

SELECTION_POLICY = """
You are RIA's reminder-selection assistant.

The user wishes to snooze an existing reminder.
Choose exactly one reminder from the supplied pending candidates.

Return JSON:
{"decision":"select|clarify|respond","reminder_id":null,"reply":""}

For select, provide an integer candidate ID and empty reply.
For clarify, provide null and a useful question.
For respond, provide null and a natural response.

Understand reminder names, dates, times, spoken numbers,
conversation context and corrections.

If several reminders are indistinguishable, ask the user
to distinguish them. Never select arbitrarily.

If exactly one reminder matches the user's description,
select it even when the user does not say its database ID.

Do not infer that a number represents an ID without context.
Only select IDs present in the candidate list.
Never modify reminders or claim a snooze succeeded.
Return JSON only.
"""

SELECTION_CODE = """
import json, os, sys
from groq import Groq

payload = json.load(sys.stdin)
result = Groq(
    api_key=os.environ["GROQ_API_KEY"],
    timeout=15.0,
    max_retries=1,
).chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role": "system", "content": sys.argv[1]},
        {"role": "user", "content": json.dumps(payload)},
    ],
    temperature=0,
    response_format={"type": "json_object"},
    max_completion_tokens=350,
)
print(result.choices[0].message.content)
"""


def _initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS reminder_snooze_proposals (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            reminder_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            due_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS durable_reminder_snoozes (
            request_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            reminder_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            expected_due_at INTEGER NOT NULL,
            minutes INTEGER,
            due_at INTEGER,
            status TEXT NOT NULL,
            result_json TEXT
        )
    """)


def _select(message, candidates, history):
    process = subprocess.run(
        [str(PYTHON), "-c", SELECTION_CODE, SELECTION_POLICY],
        input=json.dumps({
            "message": message,
            "candidates": candidates,
            "history": history,
        }),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        timeout=35,
        check=False,
    )

    if process.returncode:
        raise RuntimeError("Snooze selection unavailable")

    decision = json.loads(process.stdout)

    if not isinstance(decision, dict) or set(decision) != {
        "decision", "reminder_id", "reply"
    }:
        raise ValueError("Invalid snooze selection")

    kind = decision["decision"]
    reply = decision["reply"]

    if kind == "select":
        if reply:
            raise ValueError("Selection cannot claim completion")
        return validate_selected_reminder(
            decision["reminder_id"], candidates
        ), None

    if kind not in {"clarify", "respond"}:
        raise ValueError("Invalid selection decision")

    if decision["reminder_id"] is not None:
        raise ValueError("Unexpected reminder ID")

    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("Missing selection reply")

    return None, {
        "action": kind,
        "success": kind == "respond",
        "reply": reply.strip(),
    }


def _pending(session_id, user_id):
    get_history(session_id, user_id)

    with _ledger_connect() as db:
        _initialize(db)
        row = db.execute(
            "SELECT * FROM reminder_snooze_proposals "
            "WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        ).fetchone()

    if row is None:
        return None

    record = dict(row)

    if time.time() - record["created_at"] >= TTL:
        _discard(session_id, user_id)
        return None

    return record


def _discard(session_id, user_id):
    with _ledger_connect() as db:
        _initialize(db)
        db.execute(
            "DELETE FROM reminder_snooze_proposals "
            "WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        )


def _stage(session_id, user_id, candidate):
    get_history(session_id, user_id)

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        existing = db.execute(
            "SELECT * FROM reminder_snooze_proposals "
            "WHERE session_id=?",
            (session_id,),
        ).fetchone()

        if existing is not None:
            if (
                existing["user_id"] != user_id
                or existing["reminder_id"] != candidate["id"]
            ):
                raise PermissionError(
                    "Another snooze selection is pending"
                )
            return

        db.execute(
            """
            INSERT INTO reminder_snooze_proposals
            (session_id,user_id,reminder_id,title,due_at,created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                session_id, user_id, candidate["id"],
                candidate["title"], candidate["due_at"],
                int(time.time()),
            ),
        )


def _recover(record):
    from urllib.parse import quote

    try:
        result = request_reminders(
            "GET",
            "/reminders/snoozes/by-request/"
            + quote(record["request_id"], safe=""),
        )
    except Exception:
        return None

    if (
        not isinstance(result, dict)
        or result.get("id") != record["reminder_id"]
        or result.get("title") != record["title"]
        or result.get("status") != "pending"
        or type(result.get("due_at")) is not int
    ):
        return None

    if record["due_at"] is not None:
        if result["due_at"] != record["due_at"]:
            return None

    return result


def _execute(session_id, request_id, user_id, proposal, decision):
    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid snooze request ID")

    minutes = decision["minutes"]
    due_at = decision["due_at"]

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        previous = db.execute(
            "SELECT * FROM durable_reminder_snoozes "
            "WHERE request_id=?",
            (request_id,),
        ).fetchone()

        if previous is None:
            db.execute(
                """
                INSERT INTO durable_reminder_snoozes
                (request_id,session_id,user_id,reminder_id,
                 title,expected_due_at,minutes,due_at,status)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    request_id, session_id, user_id,
                    proposal["reminder_id"], proposal["title"],
                    proposal["due_at"], minutes, due_at, "pending",
                ),
            )
            fresh = True
        else:
            fresh = False

    if fresh:
        record = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "reminder_id": proposal["reminder_id"],
            "title": proposal["title"],
            "expected_due_at": proposal["due_at"],
            "minutes": minutes,
            "due_at": due_at,
        }
    else:
        record = dict(previous)

        if (
            record["session_id"] != session_id
            or record["user_id"] != user_id
            or record["reminder_id"] != proposal["reminder_id"]
            or record["title"] != proposal["title"]
            or record["expected_due_at"] != proposal["due_at"]
            or record["minutes"] != minutes
            or record["due_at"] != due_at
        ):
            raise PermissionError("Snooze request identity mismatch")

        if record["status"] == "completed":
            return json.loads(record["result_json"])

    # Never repeat a POST for an existing pending claim.
    if fresh:
        try:
            result = request_reminders(
                "POST",
                f"/reminders/{record['reminder_id']}/snooze-safe",
                {
                    "request_id": request_id,
                    "expected_title": record["title"],
                    "expected_due_at": record["expected_due_at"],
                    "minutes": record["minutes"],
                    "due_at": record["due_at"],
                },
            )
        except Exception:
            result = _recover(record)
    else:
        result = _recover(record)

    if result is None:
        raise RuntimeError(
            "Snooze outcome uncertain; do not retry automatically"
        )

    if (
        result.get("id") != record["reminder_id"]
        or result.get("title") != record["title"]
        or result.get("status") != "pending"
        or type(result.get("due_at")) is not int
        or (
            record["due_at"] is not None
            and result["due_at"] != record["due_at"]
        )
    ):
        raise RuntimeError("Unverified snooze result")

    from datetime import datetime

    scheduled = datetime.fromtimestamp(result["due_at"])
    date_text = scheduled.strftime("%A, %B %d")
    time_text = scheduled.strftime("%I:%M %p").lstrip("0")

    title = record["title"]

    if record["minutes"] is not None:
        duration = record["minutes"]
        if duration % 1440 == 0:
            amount = duration // 1440
            unit = "day" if amount == 1 else "days"
        elif duration % 60 == 0:
            amount = duration // 60
            unit = "hour" if amount == 1 else "hours"
        else:
            amount = duration
            unit = "minute" if amount == 1 else "minutes"

        reply = (
            f"Done! I've snoozed your {title} reminder "
            f"for {amount} {unit}. "
            f"It's now set for {date_text} at {time_text}."
        )
    else:
        reply = (
            f"Done! Your {title} reminder is now set "
            f"for {date_text} at {time_text}."
        )

    response = {
        "action": "reminder_snoozed",
        "success": True,
        "reply": reply,
        "reminder": result,
        "reset_session": True,
    }

    with _ledger_connect() as db:
        db.execute(
            """
            UPDATE durable_reminder_snoozes
            SET status='completed', result_json=?
            WHERE request_id=?
            """,
            (json.dumps(response), request_id),
        )

    _discard(session_id, user_id)
    return response


def handle_snooze_followup(
    message, session_id, request_id, user_id=OWNER
):
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    proposal = _pending(session_id, user_id)
    if proposal is None:
        return None

    reminder = request_reminders(
        "GET", f"/reminders/{proposal['reminder_id']}"
    )

    # The trusted API also rechecks this snapshot atomically.
    if (
        reminder.get("status") != "pending"
        or reminder.get("title") != proposal["title"]
        or reminder.get("due_at") != proposal["due_at"]
    ):
        _discard(session_id, user_id)
        return {
            "action": "clarify",
            "success": False,
            "reply": "That reminder has changed. Please start again.",
        }

    decision = interpret_snooze(
        message, reminder, get_history(session_id, user_id)
    )
    kind = decision["decision"]

    if kind == "clarify":
        return {
            "action": "clarify",
            "success": False,
            "reply": decision["reply"],
        }

    if kind == "cancel_snooze":
        _discard(session_id, user_id)
        return {
            "action": "respond",
            "success": True,
            "reply": "Okay, I'll leave your reminder unchanged.",
        }

    if kind == "unrelated":
        _discard(session_id, user_id)
        return None

    if kind == "cancel_reminder":
        _discard(session_id, user_id)
        from ria1.scripts.module22_reminder_confirmations import (
            stage_cancellation,
        )
        stage_cancellation(
            session_id, proposal["reminder_id"], user_id
        )
        return {
            "action": "cancel_confirmation_required",
            "success": False,
            "reply": (
                f"Do you want me to cancel your "
                f"{proposal['title']} reminder instead?"
            ),
        }

    return _execute(
        session_id, request_id, user_id, proposal, decision
    )


def begin_snooze(message, session_id, request_id, user_id=OWNER):
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    history = get_history(session_id, user_id)
    candidates = list_pending_reminders()

    if not candidates:
        return {
            "action": "respond",
            "success": True,
            "reply": "You don't have any pending reminders.",
        }

    selected, response = _select(message, candidates, history)
    if response is not None:
        return response

    # Re-read the exact reminder before storing its identity.
    current = request_reminders(
        "GET", f"/reminders/{selected['id']}"
    )

    if (
        current.get("status") != "pending"
        or current.get("title") != selected["title"]
        or current.get("due_at") != selected["due_at"]
    ):
        raise RuntimeError("Selected reminder changed")

    _stage(session_id, user_id, selected)

    # Handles both "snooze my exercise reminder" and
    # "snooze it for two hours" without requiring fixed phrases.
    return handle_snooze_followup(
        message, session_id, request_id, user_id
    )
