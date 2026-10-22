"""RIA P1.10: bounded, expiring multi-turn conversation storage."""

import json
import re
import time
import uuid

from ria1.scripts.module15_tool_executor import (
    OWNER,
    _ledger_connect,
)

TTL_SECONDS = 20 * 60
MAX_TURNS = 12


def _initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS native_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS native_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            request_id TEXT NOT NULL UNIQUE,
            user_message TEXT NOT NULL,
            assistant_reply TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)


def new_session(user_id=OWNER):
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    session_id = uuid.uuid4().hex
    now = int(time.time())

    with _ledger_connect() as db:
        _initialize(db)
        db.execute(
            """
            INSERT INTO native_sessions
            (session_id, user_id, updated_at)
            VALUES (?, ?, ?)
            """,
            (session_id, user_id, now),
        )

    return session_id


def _check_session(db, session_id, user_id):
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    if (
        not isinstance(session_id, str)
        or not re.fullmatch(r"[a-f0-9]{32}", session_id)
    ):
        raise ValueError("Invalid native session ID")

    row = db.execute(
        """
        SELECT user_id, updated_at
        FROM native_sessions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()

    if row is None:
        raise ValueError("Unknown session")

    if row["user_id"] != user_id:
        raise PermissionError("Session owner mismatch")

    if int(time.time()) - row["updated_at"] >= TTL_SECONDS:
        raise ValueError("Session expired")


def get_history(session_id, user_id=OWNER):
    with _ledger_connect() as db:
        _initialize(db)
        _check_session(db, session_id, user_id)

        rows = db.execute(
            """
            SELECT user_message, assistant_reply
            FROM native_turns
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, MAX_TURNS),
        ).fetchall()

    messages = []

    for row in reversed(rows):
        messages.append({
            "role": "user",
            "content": row["user_message"],
        })
        messages.append({
            "role": "assistant",
            "content": row["assistant_reply"],
        })

    return messages


def append_turn(
    session_id,
    request_id,
    user_message,
    assistant_reply,
    user_id=OWNER,
):
    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    for value in (user_message, assistant_reply):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Empty conversation turn")
        if len(value) > 4000:
            raise ValueError("Conversation turn too long")

    now = int(time.time())

    with _ledger_connect() as db:
        _initialize(db)
        db.execute("BEGIN IMMEDIATE")
        _check_session(db, session_id, user_id)

        previous = db.execute(
            """
            SELECT session_id, user_message, assistant_reply
            FROM native_turns
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if previous is not None:
            if (
                previous["session_id"] != session_id
                or previous["user_message"] != user_message
                or previous["assistant_reply"] != assistant_reply
            ):
                raise ValueError("Conflicting conversation request")
            return False

        db.execute(
            """
            INSERT INTO native_turns
            (session_id, request_id, user_message,
             assistant_reply, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                request_id,
                user_message.strip(),
                assistant_reply.strip(),
                now,
            ),
        )

        db.execute(
            """
            UPDATE native_sessions
            SET updated_at = ?
            WHERE session_id = ?
            """,
            (now, session_id),
        )

        db.execute(
            """
            DELETE FROM native_turns
            WHERE session_id = ?
              AND id NOT IN (
                  SELECT id FROM native_turns
                  WHERE session_id = ?
                  ORDER BY id DESC
                  LIMIT ?
              )
            """,
            (session_id, session_id, MAX_TURNS),
        )

    return True


def delete_session(session_id, user_id=OWNER):
    with _ledger_connect() as db:
        _initialize(db)
        db.execute("BEGIN IMMEDIATE")
        _check_session(db, session_id, user_id)

        db.execute(
            "DELETE FROM native_turns WHERE session_id = ?",
            (session_id,),
        )
        db.execute(
            "DELETE FROM native_sessions WHERE session_id = ?",
            (session_id,),
        )


def cleanup_expired():
    cutoff = int(time.time()) - TTL_SECONDS

    with _ledger_connect() as db:
        _initialize(db)
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            DELETE FROM native_turns
            WHERE session_id IN (
                SELECT session_id
                FROM native_sessions
                WHERE updated_at <= ?
            )
        """, (cutoff,))
        db.execute(
            "DELETE FROM native_sessions WHERE updated_at <= ?",
            (cutoff,),
        )
