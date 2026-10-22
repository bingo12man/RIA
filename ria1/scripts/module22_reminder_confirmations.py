"""RIA P1.10.8.2: session-bound reminder cancellation proposals.

This module never cancels a reminder. It only stores and verifies a
short-lived proposal to cancel one exact reminder.
"""

import time

from ria1.scripts.module15_tool_executor import OWNER, _ledger_connect
from ria1.scripts.module20_native_sessions import get_history

CONFIRMATION_TTL_SECONDS = 5 * 60


def _initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS reminder_cancel_confirmations (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            reminder_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            due_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)


def _check_session(session_id, user_id):
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    # Validates session format, ownership and expiration.
    get_history(session_id, user_id)


def _read_reminder(reminder_id):
    from ria1.scripts.module8_command_executor import request_reminders

    if type(reminder_id) is not int or reminder_id < 1:
        raise ValueError("Invalid reminder ID")

    reminder = request_reminders(
        "GET",
        f"/reminders/{reminder_id}",
    )

    if (
        not isinstance(reminder, dict)
        or type(reminder.get("id")) is not int
        or reminder["id"] != reminder_id
        or not isinstance(reminder.get("title"), str)
        or not reminder["title"].strip()
        or type(reminder.get("due_at")) is not int
    ):
        raise ValueError("Invalid reminder response")

    return reminder


def stage_cancellation(session_id, reminder_id, user_id=OWNER):
    """Propose cancelling an exact pending reminder.

    A different reminder cannot replace an unexpired proposal.
    """

    _check_session(session_id, user_id)
    reminder = _read_reminder(reminder_id)

    if reminder.get("status") != "pending":
        raise ValueError("Reminder is no longer pending")

    now = int(time.time())

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        existing = db.execute(
            """
            SELECT * FROM reminder_cancel_confirmations
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        if existing is not None:
            if now - existing["created_at"] < CONFIRMATION_TTL_SECONDS:
                if (
                    existing["user_id"] != user_id
                    or existing["reminder_id"] != reminder_id
                ):
                    raise ValueError(
                        "Another reminder cancellation is pending"
                    )

                if (
                    existing["title"] != reminder["title"]
                    or existing["due_at"] != reminder["due_at"]
                ):
                    raise ValueError(
                        "Reminder changed; confirmation must restart"
                    )

                return dict(existing)

            db.execute(
                """
                DELETE FROM reminder_cancel_confirmations
                WHERE session_id = ?
                """,
                (session_id,),
            )

        db.execute(
            """
            INSERT INTO reminder_cancel_confirmations
            (session_id, user_id, reminder_id, title, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                user_id,
                reminder_id,
                reminder["title"],
                reminder["due_at"],
                now,
            ),
        )

    return {
        "session_id": session_id,
        "user_id": user_id,
        "reminder_id": reminder_id,
        "title": reminder["title"],
        "due_at": reminder["due_at"],
        "created_at": now,
    }


def get_pending_cancellation(session_id, user_id=OWNER):
    """Read a pending proposal, without authorizing cancellation."""

    _check_session(session_id, user_id)

    with _ledger_connect() as db:
        _initialize(db)

        row = db.execute(
            """
            SELECT * FROM reminder_cancel_confirmations
            WHERE session_id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()

    if row is None:
        return None

    proposal = dict(row)

    if (
        int(time.time()) - proposal["created_at"]
        >= CONFIRMATION_TTL_SECONDS
    ):
        return None

    reminder = _read_reminder(proposal["reminder_id"])

    if (
        reminder["status"] != "pending"
        or reminder["title"] != proposal["title"]
        or reminder["due_at"] != proposal["due_at"]
    ):
        return None

    return proposal


def discard_pending_cancellation(session_id, user_id=OWNER):
    """Discard a proposal without changing the reminder."""

    _check_session(session_id, user_id)

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        cursor = db.execute(
            """
            DELETE FROM reminder_cancel_confirmations
            WHERE session_id = ? AND user_id = ?
            """,
            (session_id, user_id),
        )

    return cursor.rowcount == 1


# RIA_P11089_SINGLE_USE_CONFIRMATION
def reserve_cancellation(
    session_id,
    request_id,
    user_id=OWNER,
):
    """Atomically reserve one confirmation for one request ID.

    Returns the bound reminder snapshot. Does not cancel it.
    A reservation cannot be transferred to another request.
    """

    import re

    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    _check_session(session_id, user_id)
    now = int(time.time())

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        db.execute("""
            CREATE TABLE IF NOT EXISTS reminder_cancel_reservations (
                request_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                reminder_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                due_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'reserved'
            )
        """)

        previous = db.execute(
            """
            SELECT * FROM reminder_cancel_reservations
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if previous is not None:
            if (
                previous["session_id"] != session_id
                or previous["user_id"] != user_id
            ):
                raise PermissionError(
                    "Confirmation request belongs to another session"
                )
            return dict(previous)

        existing = db.execute(
            """
            SELECT request_id FROM reminder_cancel_reservations
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        if existing is not None:
            raise ValueError(
                "Confirmation already reserved by another request"
            )

        proposal = db.execute(
            """
            SELECT * FROM reminder_cancel_confirmations
            WHERE session_id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()

        if proposal is None:
            raise ValueError("No pending cancellation confirmation")

        if now - proposal["created_at"] >= CONFIRMATION_TTL_SECONDS:
            raise ValueError("Cancellation confirmation expired")

        db.execute(
            """
            INSERT INTO reminder_cancel_reservations
            (request_id, session_id, user_id, reminder_id,
             title, due_at, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'reserved')
            """,
            (
                request_id,
                session_id,
                user_id,
                proposal["reminder_id"],
                proposal["title"],
                proposal["due_at"],
                now,
            ),
        )

        return {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "reminder_id": proposal["reminder_id"],
            "title": proposal["title"],
            "due_at": proposal["due_at"],
            "created_at": now,
            "status": "reserved",
        }


# RIA_P110811_RESERVATION_VALIDATION
def validate_reserved_cancellation(
    session_id,
    request_id,
    user_id=OWNER,
):
    """Validate a reserved cancellation before execution.

    Read-only. Does not cancel or consume a reminder.
    """

    import re

    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    _check_session(session_id, user_id)

    now = int(time.time())

    with _ledger_connect() as db:
        _initialize(db)

        row = db.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table'
              AND name = 'reminder_cancel_reservations'
            """
        ).fetchone()

        if row is None:
            raise ValueError("No cancellation reservation")

        reservation = db.execute(
            """
            SELECT *
            FROM reminder_cancel_reservations
            WHERE request_id = ?
              AND session_id = ?
              AND user_id = ?
            """,
            (request_id, session_id, user_id),
        ).fetchone()

    if reservation is None:
        raise PermissionError("No matching cancellation authorization")

    record = dict(reservation)

    if record["status"] != "reserved":
        raise ValueError("Cancellation authorization is not active")

    if (
        now - record["created_at"]
        >= CONFIRMATION_TTL_SECONDS
    ):
        raise ValueError("Cancellation authorization expired")

    reminder = _read_reminder(record["reminder_id"])

    if reminder.get("status") != "pending":
        raise ValueError("Reminder is no longer pending")

    if (
        reminder["title"] != record["title"]
        or reminder["due_at"] != record["due_at"]
    ):
        raise ValueError(
            "Reminder changed after confirmation"
        )

    return record
