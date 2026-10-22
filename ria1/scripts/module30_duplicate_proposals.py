"""Session-bound proposals for intentional duplicate reminders.

This module never creates reminders.
"""

import json
import time

from ria1.scripts.module15_tool_executor import OWNER, _ledger_connect
from ria1.scripts.module20_native_sessions import get_history

TTL_SECONDS = 300
CREATE_TOOLS = {"reminder_create", "reminder_create_absolute"}


def _initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS duplicate_reminder_proposals (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            args_json TEXT NOT NULL,
            original_request_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            original_reminder_id INTEGER
        )
    """)
    columns = {
        row["name"]
        for row in db.execute(
            "PRAGMA table_info(duplicate_reminder_proposals)"
        )
    }
    if "original_reminder_id" not in columns:
        db.execute(
            "ALTER TABLE duplicate_reminder_proposals "
            "ADD COLUMN original_reminder_id INTEGER"
        )


def _check(session_id, user_id):
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")
    get_history(session_id, user_id)


def stage_duplicate(session_id, tool_name, args, request_id, user_id=OWNER, *, original_reminder_id=None):
    _check(session_id, user_id)

    if tool_name not in CREATE_TOOLS:
        raise ValueError("Invalid creation tool")
    if not isinstance(args, dict):
        raise ValueError("Invalid reminder arguments")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("Invalid request ID")

    # RIA_P110860_DURABLE_ORIGINAL_ID
    if type(original_reminder_id) is not int or original_reminder_id <= 0:
        raise ValueError("Original reminder ID is required")

    now = int(time.time())
    serialized = json.dumps(args, sort_keys=True)

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        existing = db.execute(
            "SELECT * FROM duplicate_reminder_proposals WHERE session_id=?",
            (session_id,),
        ).fetchone()

        if existing and now - existing["created_at"] < TTL_SECONDS:
            if (
                existing["user_id"] != user_id
                or existing["tool_name"] != tool_name
                or existing["args_json"] != serialized
                or existing["original_reminder_id"] != original_reminder_id
            ):
                raise ValueError("Another duplicate proposal is pending")
            return dict(existing)

        db.execute(
            "DELETE FROM duplicate_reminder_proposals WHERE session_id=?",
            (session_id,),
        )
        db.execute(
            """
            INSERT INTO duplicate_reminder_proposals
            (session_id, user_id, tool_name, args_json,
             original_request_id, created_at, original_reminder_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, user_id, tool_name, serialized,
                request_id, now, original_reminder_id,
            ),
        )

    return get_pending_duplicate(session_id, user_id)


def get_pending_duplicate(session_id, user_id=OWNER):
    _check(session_id, user_id)

    with _ledger_connect() as db:
        _initialize(db)
        row = db.execute(
            "SELECT * FROM duplicate_reminder_proposals WHERE session_id=?",
            (session_id,),
        ).fetchone()

    if not row:
        return None

    if row["user_id"] != user_id:
        raise PermissionError("Proposal owner mismatch")

    if int(time.time()) - row["created_at"] >= TTL_SECONDS:
        return None

    result = dict(row)
    result["arguments"] = json.loads(result["args_json"])
    return result


def discard_duplicate(session_id, user_id=OWNER):
    _check(session_id, user_id)

    with _ledger_connect() as db:
        _initialize(db)
        db.execute(
            "DELETE FROM duplicate_reminder_proposals WHERE session_id=?",
            (session_id,),
        )




# RIA_P110826_DUPLICATE_RESERVATION
def reserve_duplicate(session_id, request_id, user_id=OWNER):
    """Atomically bind a pending duplicate proposal to one approval."""

    import re

    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid confirmation request ID")

    _check(session_id, user_id)
    now = int(time.time())

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)

        db.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_reminder_reservations (
                session_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                original_request_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                original_reminder_id INTEGER
            )
        """)
        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(duplicate_reminder_reservations)"
            )
        }
        if "original_reminder_id" not in columns:
            db.execute(
                "ALTER TABLE duplicate_reminder_reservations "
                "ADD COLUMN original_reminder_id INTEGER"
            )

        existing = db.execute(
            """
            SELECT * FROM duplicate_reminder_reservations
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        if existing is not None:
            if (
                existing["request_id"] != request_id
                or existing["user_id"] != user_id
            ):
                raise ValueError(
                    "Duplicate confirmation already reserved"
                )
            return dict(existing)

        proposal = db.execute(
            """
            SELECT * FROM duplicate_reminder_proposals
            WHERE session_id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()

        if proposal is None:
            raise ValueError("No pending duplicate confirmation")

        if now - proposal["created_at"] >= TTL_SECONDS:
            raise ValueError("Duplicate confirmation expired")

        if (
            type(proposal["original_reminder_id"]) is not int
            or proposal["original_reminder_id"] <= 0
        ):
            raise PermissionError("Proposal has no bound reminder ID")

        db.execute(
            """
            INSERT INTO duplicate_reminder_reservations
            (session_id, request_id, original_request_id,
             user_id, tool_name, args_json, created_at,
             original_reminder_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                request_id,
                proposal["original_request_id"],
                user_id,
                proposal["tool_name"],
                proposal["args_json"],
                now,
                proposal["original_reminder_id"],
            ),
        )

        return {
            "session_id": session_id,
            "request_id": request_id,
            "original_request_id": proposal["original_request_id"],
            "user_id": user_id,
            "tool_name": proposal["tool_name"],
            "args_json": proposal["args_json"],
            "original_reminder_id": proposal["original_reminder_id"],
            "created_at": now,
        }


def get_reserved_duplicate(session_id, request_id, user_id=OWNER):
    """Read a previously reserved approval without executing anything."""

    _check(session_id, user_id)

    with _ledger_connect() as db:
        _initialize(db)

        row = db.execute(
            """
            SELECT * FROM sqlite_master
            WHERE type = 'table'
              AND name = 'duplicate_reminder_reservations'
            """
        ).fetchone()

        if row is None:
            return None

        reservation = db.execute(
            """
            SELECT * FROM duplicate_reminder_reservations
            WHERE session_id = ?
              AND request_id = ?
              AND user_id = ?
            """,
            (session_id, request_id, user_id),
        ).fetchone()

    if reservation is None:
        return None

    result = dict(reservation)
    result["arguments"] = json.loads(result["args_json"])
    return result


# RIA_P110829_VALIDATE_RESERVED_DUPLICATE
def validate_reserved_duplicate(session_id, request_id, user_id=OWNER):
    """Validate authorization for a NEW duplicate creation.

    Does not create a reminder.
    Previously started executions must use durable recovery instead.
    """

    reservation = get_reserved_duplicate(
        session_id, request_id, user_id
    )

    if reservation is None:
        raise PermissionError("No matching duplicate reservation")

    now = int(time.time())

    if now - reservation["created_at"] >= TTL_SECONDS:
        raise PermissionError("Duplicate approval expired")

    with _ledger_connect() as db:
        _initialize(db)

        proposal = db.execute(
            """
            SELECT *
            FROM duplicate_reminder_proposals
            WHERE session_id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()

    if proposal is None:
        raise PermissionError("Duplicate proposal was discarded")

    if now - proposal["created_at"] >= TTL_SECONDS:
        raise PermissionError("Duplicate proposal expired")

    if (
        proposal["original_request_id"]
        != reservation["original_request_id"]
        or proposal["tool_name"] != reservation["tool_name"]
        or proposal["args_json"] != reservation["args_json"]
    ):
        raise PermissionError("Duplicate proposal changed")

    return reservation
