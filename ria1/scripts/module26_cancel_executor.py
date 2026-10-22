"""RIA P1.10.8.15 — Durable, authorized reminder cancellation.

Never interprets natural language.
Never creates confirmation authorization.
Never repeats a cancellation POST after an uncertain outcome.
"""

import json
import re

from ria1.scripts.module15_tool_executor import OWNER, _ledger_connect
from ria1.scripts.module22_reminder_confirmations import (
    validate_reserved_cancellation,
)


def _initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS durable_reminder_cancellations (
            request_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            reminder_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            due_at INTEGER NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT
        )
    """)


def _recover(record):
    """GET only. A failed lookup never permits another POST."""
    from urllib.parse import quote
    from ria1.scripts.module8_command_executor import request_reminders

    try:
        recovered = request_reminders(
            "GET",
            "/reminders/cancellations/by-request/"
            + quote(record["request_id"], safe=""),
        )
    except Exception:
        return None

    if not isinstance(recovered, dict):
        return None

    if (
        recovered.get("request_id") != record["request_id"]
        or type(recovered.get("reminder_id")) is not int
        or recovered["reminder_id"] != record["reminder_id"]
        or recovered.get("expected_title") != record["title"]
        or type(recovered.get("expected_due_at")) is not int
        or recovered["expected_due_at"] != record["due_at"]
    ):
        return None

    result = recovered.get("result")

    if (
        not isinstance(result, dict)
        or type(result.get("id")) is not int
        or result["id"] != record["reminder_id"]
        or result.get("title") != record["title"]
        or type(result.get("due_at")) is not int
        or result["due_at"] != record["due_at"]
        or result.get("status") != "cancelled"
    ):
        return None

    return result


def _response(reminder):
    return {
        "action": "reminder_cancelled",
        "success": True,
        "reminder": reminder,
        "reply": "Done! I've cancelled that reminder.",
    }


def _mark_completed(request_id, result):
    response = _response(result)

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """
            UPDATE durable_reminder_cancellations
            SET status = 'completed', result_json = ?
            WHERE request_id = ?
            """,
            (json.dumps(response), request_id),
        )

    return response


def execute_confirmed_cancellation(
    session_id,
    request_id,
    user_id=OWNER,
):
    """Execute a previously reserved, explicitly confirmed cancellation."""

    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    from ria1.scripts.module8_command_executor import request_reminders

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        previous = db.execute(
            """
            SELECT * FROM durable_reminder_cancellations
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if previous is not None:
            record = dict(previous)

            if (
                record["session_id"] != session_id
                or record["user_id"] != user_id
            ):
                raise PermissionError("Cancellation request mismatch")

            if record["status"] == "completed":
                return json.loads(record["result_json"])

            # Pending or uncertain: reconcile by GET only.
            # Never send another POST.
            recover_only = True

        else:
            recover_only = False

    if recover_only:
        recovered = _recover(record)

        if recovered is None:
            raise RuntimeError(
                "Cancellation outcome uncertain; do not retry automatically"
            )

        return _mark_completed(request_id, recovered)

    # Only a new operation can reach this point.
    # Authorization must have been reserved by the gateway.
    reservation = validate_reserved_cancellation(
        session_id,
        request_id,
        user_id,
    )

    record = {
        "request_id": request_id,
        "session_id": session_id,
        "user_id": user_id,
        "reminder_id": reservation["reminder_id"],
        "title": reservation["title"],
        "due_at": reservation["due_at"],
    }

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        # Fail closed if another request raced with this one.
        existing = db.execute(
            """
            SELECT request_id
            FROM durable_reminder_cancellations
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if existing is not None:
            raise RuntimeError(
                "Concurrent cancellation request; retry outcome lookup"
            )

        db.execute(
            """
            INSERT INTO durable_reminder_cancellations
            (request_id, session_id, user_id, reminder_id,
             title, due_at, status, result_json)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)
            """,
            (
                request_id,
                session_id,
                user_id,
                record["reminder_id"],
                record["title"],
                record["due_at"],
            ),
        )

    # Pending record has committed before the external write.
    try:
        result = request_reminders(
            "POST",
            f"/reminders/{record['reminder_id']}/cancel",
            {
                "request_id": request_id,
                "expected_title": record["title"],
                "expected_due_at": record["due_at"],
            },
        )

        if (
            not isinstance(result, dict)
            or result.get("id") != record["reminder_id"]
            or result.get("title") != record["title"]
            or result.get("due_at") != record["due_at"]
            or result.get("status") != "cancelled"
        ):
            raise RuntimeError("Unverified cancellation response")

        return _mark_completed(request_id, result)

    except Exception as exc:
        recovered = _recover(record)

        if recovered is not None:
            return _mark_completed(request_id, recovered)

        with _ledger_connect() as db:
            db.execute(
                """
                UPDATE durable_reminder_cancellations
                SET status = 'uncertain'
                WHERE request_id = ?
                """,
                (request_id,),
            )

        raise RuntimeError(
            "Cancellation outcome uncertain; check reminders before retrying"
        ) from exc
