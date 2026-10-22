"""RIA: GPT-OSS reminder done, skip and reschedule coordinator."""

import json
import re
import time
from datetime import datetime


from ria1.scripts.module15_tool_executor import OWNER, _ledger_connect
from ria1.scripts.module20_native_sessions import get_history
from ria1.scripts.module23_reminder_discovery import list_pending_reminders
from ria1.scripts.module8_command_executor import request_reminders

POLICY = """
You select an existing reminder for a user-requested action.

Return exactly this JSON structure:
{
  "decision": "execute|clarify|respond",
  "action": "done|skip|reschedule|null",
  "reminder_id": null,
  "scheduled_at": null,
  "reply": ""
}

Rules:
- Match only the supplied pending reminder candidates.
- Understand names, dates, times, follow-ups and corrections.
- Use conversation history only to complete an unfinished request.

- Treat the latest user message as the primary instruction.
- Previous conversation context is supporting evidence, not authorization.
- A reminder name alone does not authorize any modification.
- Example: "My reading reminder" -> clarify:
  "What would you like me to do with your reading reminder?"
- Do not assume a reschedule merely because an earlier turn
  mentioned a time.
- For a genuine follow-up such as "Move it to 8 AM",
  use history only when one specific reminder is clearly established.
- If multiple reminders could match, ask which one.
- If the latest message contradicts the earlier request,
  follow the latest explicit instruction.
- A new unrelated request must not inherit an old reminder action.
- Do not propose a new time unless the user requested rescheduling.
- After an unclear transcription, ask what the user intended
  instead of guessing the missing action.

- Never select an arbitrary reminder when multiple matches exist.
- 'Done' means the user completed the task.
- 'Skip' means the user intentionally wants to skip the reminder.
- Reschedule modifies an existing reminder, not creates another.
- For reschedule, scheduled_at must be an ISO-8601 future datetime
  with an explicit UTC offset, using supplied local date/time.
- Never guess missing clock times or AM/PM.
- If an essential detail is missing, clarify.
- Do not execute hypothetical, negated or quoted instructions.
- NEGATION SAFETY: A negative instruction is not authorization
  to perform a different reminder action.
- "Don't mark exercise done" means leave exercise unchanged.
  It does NOT mean skip exercise.
- "Don't skip exercise" does NOT mean mark it done.
- "Don't reschedule exercise" does NOT mean cancel it.
- When the user says not to perform an action, return respond
  with action=null, reminder_id=null, scheduled_at=null,
  and a short acknowledgement.
- Only perform done, skip or reschedule when the user
  affirmatively requests that exact action.
- If the user says "Don't mark it done; skip it instead",
  the explicit affirmative "skip it instead" can authorize skip
  after resolving the intended reminder unambiguously.
- If the request is unrelated, respond without performing an action.
- On execute, reply must be empty.
- On clarify/respond, reminder_id and scheduled_at must be null.
- Never claim success before the trusted backend executes.
- Return JSON only.
"""


def _initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS durable_manage_actions (
            request_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            reminder_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            expected_due_at INTEGER NOT NULL,
            action TEXT NOT NULL,
            due_at INTEGER,
            status TEXT NOT NULL,
            result_json TEXT
        )
    """)


def _decide(message, history, candidates):
    import os
    import subprocess
    import tempfile

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing")
    if "\\n" in key or "\\r" in key:
        raise ValueError("Invalid API key")

    now = datetime.now().astimezone()

    request_body = {
        "model": "openai/gpt-oss-120b",
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": POLICY},
            {
                "role": "user",
                "content": json.dumps({
                    "message": message,
                    "history": history,
                    "candidates": candidates,
                    "local_datetime": now.isoformat(),
                    "timezone": str(now.tzinfo),
                }),
            },
        ],
    }

    def quote(value):
        return '"' + value.replace("\\\\", "\\\\\\\\").replace('"', '\\"') + '"'

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as body:
        json.dump(request_body, body)
        body.flush()

        config = "\n".join([
            "silent",
            "show-error",
            "fail-with-body",
            "max-time = 20",
            'request = "POST"',
            "url = " + quote(
                "https://api.groq.com/openai/v1/chat/completions"
            ),
            "header = " + quote("Content-Type: application/json"),
            "header = " + quote("Authorization: Bearer " + key),
            "data-binary = " + quote("@" + body.name),
            "",
        ])

        process = subprocess.run(
            ["curl", "--config", "-"],
            input=config,
            capture_output=True,
            text=True,
            timeout=23,
            check=False,
        )

    if process.returncode:
        raise RuntimeError("Reminder decision request failed")

    response = json.loads(process.stdout)
    content = response["choices"][0]["message"]["content"]
    data = json.loads(content)

    expected = {
        "decision", "action", "reminder_id",
        "scheduled_at", "reply",
    }

    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError("Invalid reminder action decision")

    return data


def _recover(record):
    from urllib.parse import quote

    try:
        result = request_reminders(
            "GET",
            "/reminders/actions/by-request/"
            + quote(record["request_id"], safe=""),
        )
    except Exception:
        return None

    if not isinstance(result, dict):
        return None

    reminder = result.get("reminder")
    if not isinstance(reminder, dict):
        return None

    expected_status = {
        "done": "done",
        "skip": "skipped",
        "reschedule": "pending",
    }[record["action"]]

    expected_due = (
        record["due_at"]
        if record["action"] == "reschedule"
        else record["expected_due_at"]
    )

    if (
        result.get("request_id") != record["request_id"]
        or result.get("action") != record["action"]
        or type(reminder.get("id")) is not int
        or reminder["id"] != record["reminder_id"]
        or reminder.get("title") != record["title"]
        or type(reminder.get("due_at")) is not int
        or reminder["due_at"] != expected_due
        or reminder.get("status") != expected_status
    ):
        return None

    return result


def _execute(session_id, request_id, user_id, reminder, action, due_at):
    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        previous = db.execute(
            "SELECT * FROM durable_manage_actions WHERE request_id=?",
            (request_id,),
        ).fetchone()

        if previous is None:
            db.execute(
                """
                INSERT INTO durable_manage_actions
                (request_id,session_id,user_id,reminder_id,title,
                 expected_due_at,action,due_at,status)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    request_id, session_id, user_id,
                    reminder["id"], reminder["title"],
                    reminder["due_at"], action, due_at, "pending",
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
            "reminder_id": reminder["id"],
            "title": reminder["title"],
            "expected_due_at": reminder["due_at"],
            "action": action,
            "due_at": due_at,
        }
    else:
        record = dict(previous)
        for key, value in {
            "session_id": session_id,
            "user_id": user_id,
            "reminder_id": reminder["id"],
            "title": reminder["title"],
            "expected_due_at": reminder["due_at"],
            "action": action,
            "due_at": due_at,
        }.items():
            if record[key] != value:
                raise PermissionError("Request ID identity mismatch")

        if record["status"] == "completed":
            return json.loads(record["result_json"])

    if fresh:
        try:
            result = request_reminders(
                "POST",
                f"/reminders/{record['reminder_id']}/action-safe",
                {
                    "request_id": request_id,
                    "expected_title": record["title"],
                    "expected_due_at": record["expected_due_at"],
                    "action": record["action"],
                    "due_at": record["due_at"],
                },
            )
        except Exception:
            result = _recover(record)
    else:
        # An uncertain operation must not send another POST.
        result = _recover(record)

    if result is None:
        raise RuntimeError(
            "Reminder action outcome uncertain; "
            "do not retry automatically"
        )

    verified = _recover(record)
    if verified is None or verified != result:
        raise RuntimeError("Unverified reminder action result")

    updated = result["reminder"]
    title = updated["title"]

    if action == "done":
        reply = f"Marked {title} as done."
    elif action == "skip":
        reply = f"Skipped {title}."
    else:
        when = datetime.fromtimestamp(updated["due_at"])
        formatted = when.strftime("%A at %I:%M %p")
        reply = f"Moved {title} to {formatted}."

    response = {
        "action": {
            "done": "reminder_done",
            "skip": "reminder_skipped",
            "reschedule": "reminder_rescheduled",
        }[action],
        "success": True,
        "reply": reply,
        "reminder": updated,
        "reset_session": True,
    }

    with _ledger_connect() as db:
        db.execute(
            """
            UPDATE durable_manage_actions
            SET status='completed', result_json=?
            WHERE request_id=?
            """,
            (json.dumps(response), request_id),
        )

    return response


def handle_reminder_action(
    message, session_id, request_id, user_id=OWNER
):
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

    decision = _decide(message, history, candidates)
    kind = decision["decision"]

    if kind not in {"execute", "clarify", "respond"}:
        raise ValueError("Invalid reminder decision")

    if kind != "execute":
        if (
            decision["reminder_id"] is not None
            or decision["scheduled_at"] is not None
            or decision["action"] not in (None, "null")
            or not isinstance(decision["reply"], str)
            or not decision["reply"].strip()
        ):
            raise ValueError("Invalid clarification")

        return {
            "action": kind,
            "success": kind == "respond",
            "reply": decision["reply"].strip(),
        }

    action = decision["action"]
    reminder_id = decision["reminder_id"]

    if action not in {"done", "skip", "reschedule"}:
        raise ValueError("Invalid reminder action")

    if decision["reply"] != "":
        raise ValueError("Execution cannot claim success")

    if type(reminder_id) is not int:
        raise ValueError("Invalid reminder selection")

    matches = [
        item for item in candidates
        if item["id"] == reminder_id
    ]

    if len(matches) != 1:
        raise ValueError("Selected reminder is not a candidate")

    candidate = matches[0]

    scheduled = decision["scheduled_at"]
    due_at = None

    if action == "reschedule":
        if not isinstance(scheduled, str):
            raise ValueError("Missing reschedule date")

        parsed = datetime.fromisoformat(scheduled)

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Reschedule time must have UTC offset")

        due_at = int(parsed.timestamp())
        now = int(time.time())

        if not now < due_at <= now + 365 * 86400:
            raise ValueError("Reschedule time outside allowed range")
    elif scheduled is not None:
        raise ValueError("Unexpected date for done or skip")

    current = request_reminders(
        "GET",
        f"/reminders/{reminder_id}",
    )

    if (
        not isinstance(current, dict)
        or current.get("id") != reminder_id
        or current.get("title") != candidate["title"]
        or current.get("due_at") != candidate["due_at"]
        or current.get("status") != "pending"
    ):
        raise RuntimeError("Selected reminder changed")

    return _execute(
        session_id, request_id, user_id, current, action, due_at
    )
