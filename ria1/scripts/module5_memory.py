import os
import sqlite3
from pathlib import Path

DB_PATH = Path(
    os.getenv(
        "RIA_MEMORY_DB",
        str(Path(__file__).resolve().parents[1] / "data" / "ria_memory.db"),
    )
)

MAX_MEMORIES = 50


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, memory_key)
            )
        """)


def save_memory(user_id: str, key: str, value: str):
    user_id = user_id.strip()
    key = key.strip().lower()
    value = value.strip()

    if not user_id or not key or not value:
        raise ValueError("User, key and value are required")

    if len(user_id) > 128 or len(key) > 64 or len(value) > 500:
        raise ValueError("Memory field exceeds allowed length")

    initialize()

    with connect() as db:
        existing = db.execute(
            "SELECT 1 FROM memories WHERE user_id = ? AND memory_key = ?",
            (user_id, key),
        ).fetchone()

        count = db.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]

        if existing is None and count >= MAX_MEMORIES:
            raise ValueError("Memory limit reached")

        db.execute("""
            INSERT INTO memories (user_id, memory_key, memory_value)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, memory_key)
            DO UPDATE SET
                memory_value = excluded.memory_value,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, key, value))


def get_memories(user_id: str):
    initialize()
    with connect() as db:
        rows = db.execute("""
            SELECT memory_key, memory_value
            FROM memories
            WHERE user_id = ?
            ORDER BY memory_key
        """, (user_id,)).fetchall()

    return {
        row["memory_key"]: row["memory_value"]
        for row in rows
    }


def delete_memory(user_id: str, key: str):
    initialize()
    with connect() as db:
        result = db.execute(
            "DELETE FROM memories WHERE user_id = ? AND memory_key = ?",
            (user_id, key.strip().lower()),
        )
        return result.rowcount > 0



# RIA_P052_ATOMIC_MEMORY_REPLACE

def replace_memory(user_id: str, old_key: str, new_key: str, new_value: str):
    """Atomically replace one owned memory without creating duplicates."""
    user_id = user_id.strip()
    old_key = old_key.strip().lower()
    new_key = new_key.strip().lower()
    new_value = new_value.strip()

    if not user_id or not old_key or not new_key or not new_value:
        raise ValueError("Memory fields cannot be empty")

    if len(user_id) > 128 or len(new_key) > 64 or len(new_value) > 500:
        raise ValueError("Memory field exceeds allowed length")

    initialize()

    with connect() as db:
        existing = db.execute(
            "SELECT id FROM memories WHERE user_id = ? AND memory_key = ?",
            (user_id, old_key),
        ).fetchone()

        if existing is None:
            return False

        conflict = db.execute(
            "SELECT id FROM memories WHERE user_id = ? AND memory_key = ?",
            (user_id, new_key),
        ).fetchone()

        if conflict is not None and conflict["id"] != existing["id"]:
            raise ValueError("The replacement memory already exists")

        db.execute(
            """
            UPDATE memories
            SET memory_key = ?, memory_value = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (new_key, new_value, existing["id"], user_id),
        )

    return True

if __name__ == "__main__":
    initialize()

    user = "local_demo_user"

    save_memory(user, "instrument", "guitar")
    save_memory(user, "response_preference", "short and concise")

    print("Saved memories:", get_memories(user))

    delete_memory(user, "instrument")

    print("After deletion:", get_memories(user))
