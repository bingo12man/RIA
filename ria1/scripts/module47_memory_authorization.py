"""RIA M8.13: durable evidence for authorized memory operations."""

import json
import sqlite3
from datetime import datetime, timezone


ACTIONS = {"memory_save", "memory_update", "memory_forget"}


def initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS memory_authorizations (
            request_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            arguments_json TEXT NOT NULL,
            authorized_at TEXT NOT NULL
        )
    """)


def record_authorization(db, request_id, user_id, action, arguments):
    if action not in ACTIONS:
        raise ValueError("Unsupported memory action")

    if not all(
        isinstance(value, str) and value.strip()
        for value in (request_id, user_id)
    ):
        raise ValueError("Invalid authorization identity")

    if not isinstance(arguments, dict):
        raise ValueError("Invalid authorization arguments")

    initialize(db)

    evidence = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=False,
    )

    db.execute(
        """
        INSERT INTO memory_authorizations
        (request_id, user_id, action, arguments_json, authorized_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            request_id,
            user_id,
            action,
            evidence,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def verify_authorization(db, request_id, user_id, action, arguments):
    if not isinstance(arguments, dict):
        return False

    initialize(db)

    row = db.execute(
        """
        SELECT user_id, action, arguments_json
        FROM memory_authorizations
        WHERE request_id = ?
        """,
        (request_id,),
    ).fetchone()

    if row is None:
        return False

    expected = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=False,
    )

    return (
        row[0] == user_id
        and row[1] == action
        and row[2] == expected
    )
