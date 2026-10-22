"""Atomic memory mutations using an existing attached SQLite connection.

The caller owns the transaction and must attach the memory database
under the alias 'memorydb' before invoking this function.
"""

from ria1.scripts.module11_memory_commands import memory_key
from ria1.scripts.module5_memory import MAX_MEMORIES


def perform_atomic_memory(db, action, args, user_id):
    if action not in {"memory_save", "memory_update", "memory_forget"}:
        raise ValueError("Unsupported memory action")

    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("Invalid memory owner")

    if not isinstance(args, dict):
        raise ValueError("Invalid memory arguments")

    rows = db.execute(
        """
        SELECT memory_key, memory_value
        FROM memorydb.memories
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchall()

    existing = {
        row[0]: row[1]
        for row in rows
    }

    def exact_match(fact):
        if not isinstance(fact, str) or not fact.strip():
            raise ValueError("Invalid memory fact")

        normalized = " ".join(
            fact.strip().rstrip(".!? ").casefold().split()
        )

        matches = [
            (key, value)
            for key, value in existing.items()
            if " ".join(
                value.strip().rstrip(".!? ").casefold().split()
            ) == normalized
        ]

        if len(matches) != 1:
            raise ValueError("Exactly one saved memory must match")

        return matches[0]

    if action == "memory_save":
        if set(args) != {"fact"}:
            raise ValueError("Invalid save arguments")

        fact = args["fact"].strip()
        key = memory_key(fact)

        if not fact or len(fact) > 500:
            raise ValueError("Invalid memory length")

        if key not in existing and len(existing) >= MAX_MEMORIES:
            raise ValueError("Memory limit reached")

        db.execute(
            """
            INSERT INTO memorydb.memories
                (user_id, memory_key, memory_value)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, memory_key)
            DO UPDATE SET
                memory_value = excluded.memory_value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, key, fact),
        )

        return {"action": "memory_saved", "fact": fact}

    if action == "memory_forget":
        if set(args) != {"exact_fact"}:
            raise ValueError("Invalid forget arguments")

        key, old_fact = exact_match(args["exact_fact"])

        cursor = db.execute(
            """
            DELETE FROM memorydb.memories
            WHERE user_id = ? AND memory_key = ?
            """,
            (user_id, key),
        )

        if cursor.rowcount != 1:
            raise RuntimeError("Memory deletion failed")

        return {"action": "memory_deleted", "fact": old_fact}

    if set(args) != {"old_fact", "new_fact"}:
        raise ValueError("Invalid update arguments")

    key, old_fact = exact_match(args["old_fact"])
    new_fact = args["new_fact"].strip()
    new_key = memory_key(new_fact)

    if not new_fact or len(new_fact) > 500:
        raise ValueError("Invalid replacement memory")

    if new_key in existing and new_key != key:
        raise ValueError("Replacement memory already exists")

    cursor = db.execute(
        """
        UPDATE memorydb.memories
        SET memory_key = ?,
            memory_value = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND memory_key = ?
        """,
        (new_key, new_fact, user_id, key),
    )

    if cursor.rowcount != 1:
        raise RuntimeError("Memory replacement failed")

    return {
        "action": "memory_updated",
        "old_fact": old_fact,
        "new_fact": new_fact,
    }
