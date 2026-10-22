"""RIA: atomic, single-use claim for duplicate creation.

No reminder API calls are made by this module.
"""

import hashlib
import re
import time

from ria1.scripts.module15_tool_executor import OWNER, _ledger_connect
from ria1.scripts.module20_native_sessions import get_history
from ria1.scripts.module30_duplicate_proposals import (
    TTL_SECONDS,
    CREATE_TOOLS,
    _initialize as initialize_proposals,
)


def claim_duplicate(session_id, request_id, user_id=OWNER):
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    # Validate active session before acquiring the write transaction.
    get_history(session_id, user_id)
    now = int(time.time())

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        initialize_proposals(db)

        db.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_execution_claims (
                request_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                original_request_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                execution_id TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                original_reminder_id INTEGER
            )
        """)

        # RIA_P110860_DURABLE_ORIGINAL_ID
        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(duplicate_execution_claims)"
            )
        }
        if "original_reminder_id" not in columns:
            db.execute(
                "ALTER TABLE duplicate_execution_claims "
                "ADD COLUMN original_reminder_id INTEGER"
            )

        previous = db.execute(
            """
            SELECT * FROM duplicate_execution_claims
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if previous is not None:
            if (
                previous["session_id"] != session_id
                or previous["user_id"] != user_id
            ):
                raise PermissionError("Claim belongs to another session")

            return {
                **dict(previous),
                "new_claim": False,
            }

        existing = db.execute(
            """
            SELECT request_id FROM duplicate_execution_claims
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        if existing is not None:
            raise PermissionError(
                "Another request already claimed this proposal"
            )

        # RIA_P110831_RESERVATION_TABLE_INIT
        # Fresh ledgers have no reservation table.
        # An absent approval must fail closed, not raise SQLite errors.
        db.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_reminder_reservations (
                session_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                original_request_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

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
            raise PermissionError("No approved reservation")

        proposal = db.execute(
            """
            SELECT * FROM duplicate_reminder_proposals
            WHERE session_id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()

        if proposal is None:
            raise PermissionError("Proposal discarded")

        for record in (reservation, proposal):
            age = now - record["created_at"]

            if age < 0 or age >= TTL_SECONDS:
                raise PermissionError("Duplicate approval expired")

        for field in (
            "original_request_id",
            "tool_name",
            "args_json",
            "original_reminder_id",
        ):
            if reservation[field] != proposal[field]:
                raise PermissionError("Proposal changed")

        if reservation["tool_name"] not in CREATE_TOOLS:
            raise PermissionError("Invalid creation tool")

        original_id = reservation["original_reminder_id"]
        if type(original_id) is not int or original_id <= 0:
            raise PermissionError("Missing original reminder identity")

        execution_id = (
            "dup-"
            + hashlib.sha256(
                (
                    user_id + ":" +
                    reservation["original_request_id"]
                ).encode("utf-8")
            ).hexdigest()
        )

        db.execute(
            """
            INSERT INTO duplicate_execution_claims (
                request_id, session_id, original_request_id,
                user_id, tool_name, args_json,
                execution_id, created_at, original_reminder_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                session_id,
                reservation["original_request_id"],
                user_id,
                reservation["tool_name"],
                reservation["args_json"],
                execution_id,
                now,
                original_id,
            ),
        )

        return {
            "request_id": request_id,
            "session_id": session_id,
            "original_request_id":
                reservation["original_request_id"],
            "user_id": user_id,
            "tool_name": reservation["tool_name"],
            "args_json": reservation["args_json"],
            "execution_id": execution_id,
            "original_reminder_id": original_id,
            "created_at": now,
            "new_claim": True,
        }
