"""RIA P1.6.5: bind an execution ID to one spoken request."""

import hashlib
import sqlite3

from ria1.scripts.module15_tool_executor import (
    OWNER, _ledger_connect,
)


def bind_request(request_id, message, user_id=OWNER):
    """Prevent reuse of a request ID for different spoken text."""
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    if not isinstance(message, str) or not message.strip():
        raise ValueError("Empty request")

    import re
    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    fingerprint = hashlib.sha256(
        message.strip().encode("utf-8")
    ).hexdigest()

    with _ledger_connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS voice_requests (
                request_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                message_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("BEGIN IMMEDIATE")

        previous = db.execute(
            """
            SELECT user_id, message_hash
            FROM voice_requests
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if previous is not None:
            if (
                previous["user_id"] != user_id
                or previous["message_hash"] != fingerprint
            ):
                raise ValueError(
                    "Request ID reused for different spoken text"
                )
            return

        db.execute(
            """
            INSERT INTO voice_requests
            (request_id, user_id, message_hash)
            VALUES (?, ?, ?)
            """,
            (request_id, user_id, fingerprint),
        )
