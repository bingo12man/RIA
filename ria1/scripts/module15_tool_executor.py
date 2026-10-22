"""RIA P1.3: validated, single-user agent tool execution."""

import re
import os
import json
import sqlite3
import hashlib
from pathlib import Path
import threading
from copy import deepcopy

from ria1.scripts.module5_memory import (
    get_memories,
    save_memory,
    delete_memory,
    replace_memory,
)
from ria1.scripts.module11_memory_commands import memory_key
from ria1.scripts.module15_agent_tools import TOOL_SCHEMAS

OWNER = "ria_local_owner"
TOOL_DEFS = {
    entry["function"]["name"]: entry["function"]["parameters"]
    for entry in TOOL_SCHEMAS
}

_LOCK = threading.RLock()
_COMPLETED = {}


def _normalize(value):
    return " ".join(value.strip().rstrip(".!? ").casefold().split())


def _validate(name, arguments):
    if name not in TOOL_DEFS:
        raise ValueError("Tool is not authorized")

    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")

    spec = TOOL_DEFS[name]
    properties = spec["properties"]

    if set(arguments) != set(spec["required"]):
        raise ValueError("Missing or unexpected tool arguments")

    for key, value in arguments.items():
        field = properties[key]
        kind = field["type"]

        if kind == "string":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("A nonempty string is required")
            if len(value) > 500:
                raise ValueError("Text exceeds 500 characters")

        elif kind == "integer":
            if type(value) is not int:
                raise ValueError("An integer is required")
            if not field["minimum"] <= value <= field["maximum"]:
                raise ValueError("Time is outside the allowed range")

    return arguments


def _exact_match(user_id, fact):
    memories = get_memories(user_id)
    target = _normalize(fact)

    matches = [
        (key, value)
        for key, value in memories.items()
        if _normalize(value) == target
    ]

    if len(matches) != 1:
        raise ValueError("Exactly one saved memory must match")

    return matches[0]


def _perform(name, args, user_id, execution_id=None, duplicate_of_id=None):
    if name == "memory_list":
        return {
            "action": "memory_listed",
            "memories": get_memories(user_id),
        }

    if name == "memory_save":
        fact = args["fact"].strip()
        save_memory(user_id, memory_key(fact), fact)
        return {"action": "memory_saved", "fact": fact}

    if name == "memory_forget":
        key, old_fact = _exact_match(
            user_id, args["exact_fact"]
        )
        if not delete_memory(user_id, key):
            raise RuntimeError("Memory deletion failed")
        return {"action": "memory_deleted", "fact": old_fact}

    if name == "memory_update":
        key, old_fact = _exact_match(
            user_id, args["old_fact"]
        )
        new_fact = args["new_fact"].strip()

        changed = replace_memory(
            user_id, key, memory_key(new_fact), new_fact
        )
        if not changed:
            raise RuntimeError("Memory update failed")

        return {
            "action": "memory_updated",
            "old_fact": old_fact,
            "new_fact": new_fact,
        }

    if name == "reminder_create":
        from ria1.scripts.module8_command_executor import (
            request_reminders,
        )

        reminder = request_reminders(
            "POST",
            "/reminders",
            {
                "title": args["title"].strip(),
                "minutes_from_now": args["minutes_from_now"],
                # RIA_P183_REMINDER_REQUEST_ID
                "request_id": execution_id,
            },
        )
        return {
            "action": "reminder_created",
            "reminder": reminder,
        }

    # RIA_P11073_ABSOLUTE_EXECUTION
    if name == "reminder_create_absolute":
        from ria1.scripts.module21_absolute_time import (
            validate_scheduled_time,
        )
        from ria1.scripts.module8_command_executor import (
            request_reminders,
        )

        due_at = validate_scheduled_time(
            args["scheduled_at"],
            args["timezone"],
        )

        reminder = request_reminders(
            "POST",
            "/reminders",
            {
                "title": args["title"].strip(),
                "due_at": due_at,
                "request_id": execution_id,
                **(
                    {"duplicate_of_id": duplicate_of_id}
                    if duplicate_of_id is not None
                    else {}
                ),
            },
        )

        return {
            "action": "reminder_created",
            "reminder": reminder,
        }

    raise ValueError("Tool is not implemented")



# RIA_P15_PERSISTENT_EXECUTION

LEDGER_DB = Path(
    os.getenv(
        "RIA_AGENT_LEDGER_DB",
        str(
            Path(__file__).resolve().parents[1]
            / "data"
            / "ria_agent_actions.db"
        ),
    )
)


def _ledger_connect():
    LEDGER_DB.parent.mkdir(parents=True, exist_ok=True)

    # Restrict permissions when creating a new ledger file.
    fd = os.open(
        str(LEDGER_DB),
        os.O_CREAT | os.O_RDWR,
        0o600,
    )
    os.close(fd)

    db = sqlite3.connect(str(LEDGER_DB), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""
        CREATE TABLE IF NOT EXISTS tool_executions (
            execution_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    return db


def _request_hash(name, args, user_id):
    payload = json.dumps(
        {
            "tool": name,
            "arguments": args,
            "user_id": user_id,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


# RIA_P1842_LEDGER_RECOVERY
def _recover_reminder(execution_id, args):
    """Read-only recovery. Return None unless details match."""
    from urllib.parse import quote
    from ria1.scripts.module8_command_executor import request_reminders

    try:
        reminder = request_reminders(
            "GET",
            "/reminders/by-request/"
            + quote(execution_id, safe=""),
        )
    except Exception:
        # A failed lookup does NOT authorize another POST.
        return None

    if not isinstance(reminder, dict):
        return None

    try:
        created_at = reminder["created_at"]
        due_at = reminder["due_at"]

        if type(created_at) is not int or type(due_at) is not int:
            return None

        valid = (
            type(reminder.get("id")) is int
            and reminder.get("title") == args["title"].strip()
            and due_at - created_at
                == args["minutes_from_now"] * 60
            and reminder.get("status")
                in {"pending", "done", "skipped"}
        )
    except (KeyError, TypeError, ValueError):
        return None

    return reminder if valid else None



def _recover_absolute_reminder(execution_id, args):
    """Recover an existing reminder without creating another."""
    from datetime import datetime
    from urllib.parse import quote
    from ria1.scripts.module8_command_executor import request_reminders

    try:
        reminder = request_reminders(
            "GET",
            "/reminders/by-request/"
            + quote(execution_id, safe=""),
        )

        expected_due = int(
            datetime.fromisoformat(
                args["scheduled_at"]
            ).timestamp()
        )

        if not isinstance(reminder, dict):
            return None

        valid = (
            type(reminder.get("id")) is int
            and type(reminder.get("due_at")) is int
            and reminder["due_at"] == expected_due
            and reminder.get("title") == args["title"].strip()
            and reminder.get("status")
                in {"pending", "done", "skipped"}
        )

        return reminder if valid else None

    except Exception:
        return None




# RIA_M819_ATOMIC_MEMORY_EXECUTION
def _execute_atomic_memory(name, args, user_id, execution_id):
    """Commit a memory mutation and execution outcome together."""
    from ria1.scripts.module5_memory import DB_PATH
    from ria1.scripts.module48_atomic_memory import perform_atomic_memory

    fingerprint = _request_hash(name, args, user_id)

    with _LOCK:
        with _ledger_connect() as db:
            db.execute(
                "ATTACH DATABASE ? AS memorydb",
                (str(DB_PATH),),
            )

            db.execute("BEGIN IMMEDIATE")

            previous = db.execute(
                """
                SELECT * FROM main.tool_executions
                WHERE execution_id = ?
                """,
                (execution_id,),
            ).fetchone()

            if previous is not None:
                if (
                    previous["request_hash"] != fingerprint
                    or previous["tool_name"] != name
                    or previous["user_id"] != user_id
                ):
                    raise ValueError(
                        "Execution ID reused with different request"
                    )

                if previous["status"] == "completed":
                    return json.loads(previous["result_json"])

                raise RuntimeError(
                    "Previous memory execution is unresolved; "
                    "do not automatically repeat it"
                )

            result = perform_atomic_memory(
                db, name, args, user_id
            )

            response = {"success": True, **result}

            db.execute(
                """
                INSERT INTO main.tool_executions
                (execution_id, user_id, tool_name,
                 request_hash, status, result_json)
                VALUES (?, ?, ?, ?, 'completed', ?)
                """,
                (
                    execution_id,
                    user_id,
                    name,
                    fingerprint,
                    json.dumps(response, ensure_ascii=False),
                ),
            )

            return response



def execute_tool(name, arguments, user_id, execution_id, *, duplicate_of_id=None):
    """Execute an authorized tool with durable replay protection.

    Pending executions are never automatically repeated.
    A crash during execution requires outcome reconciliation.
    """
    if user_id != OWNER:
        raise PermissionError("Unauthorized RIA profile")

    if not isinstance(execution_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", execution_id
    ):
        raise ValueError("Invalid execution ID")

    args = _validate(name, arguments)
    # RIA_P110857_ATOMIC_DUPLICATE
    if duplicate_of_id is not None:
        if (
            name != "reminder_create_absolute"
            or type(duplicate_of_id) is not int
            or duplicate_of_id <= 0
        ):
            raise ValueError("Invalid trusted duplicate reference")

    fingerprint_args = (
        {**args, "_duplicate_of_id": duplicate_of_id}
        if duplicate_of_id is not None
        else args
    )
    fingerprint = _request_hash(name, fingerprint_args, user_id)

    if name in {"memory_save", "memory_update", "memory_forget"}:
        return _execute_atomic_memory(
            name, args, user_id, execution_id
        )

    with _LOCK:
        with _ledger_connect() as db:
            db.execute("BEGIN IMMEDIATE")

            previous = db.execute(
                """
                SELECT * FROM tool_executions
                WHERE execution_id = ?
                """,
                (execution_id,),
            ).fetchone()

            if previous is not None:
                if (
                    previous["request_hash"] != fingerprint
                    or previous["tool_name"] != name
                    or previous["user_id"] != user_id
                ):
                    raise ValueError(
                        "Execution ID reused with different request"
                    )

                if previous["status"] == "completed":
                    return json.loads(previous["result_json"])

                if name in {"reminder_create", "reminder_create_absolute"}:
                    recovered = (
                        _recover_absolute_reminder(execution_id, args)
                        if name == "reminder_create_absolute"
                        else _recover_reminder(execution_id, args)
                    )
                    if recovered is not None:
                        response = {
                            "success": True,
                            "action": "reminder_created",
                            "reminder": recovered,
                        }
                        db.execute(
                            """
                            UPDATE tool_executions
                            SET status = 'completed',
                                result_json = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE execution_id = ?
                            """,
                            (
                                json.dumps(response, ensure_ascii=False),
                                execution_id,
                            ),
                        )
                        return response

                raise RuntimeError(
                    "Previous execution remains uncertain; "
                    "do not repeat the original action"
                )

            # RIA_P11074_REPLAY_VALIDATION
            # Replays are checked before future-time validation.
            if name == "reminder_create_absolute":
                from ria1.scripts.module21_absolute_time import (
                    validate_scheduled_time,
                )
                validate_scheduled_time(
                    args["scheduled_at"],
                    args["timezone"],
                )

            db.execute(
                """
                INSERT INTO tool_executions
                (execution_id, user_id, tool_name,
                 request_hash, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (execution_id, user_id, name, fingerprint),
            )

        # Pending has been committed before any external side effect.
        try:
            result = (
                _perform(
                    name, args, user_id, execution_id,
                    duplicate_of_id=duplicate_of_id,
                )
                if duplicate_of_id is not None
                else _perform(name, args, user_id, execution_id)
            )
            response = {"success": True, **result}
        except Exception:
            if name in {"reminder_create", "reminder_create_absolute"}:
                recovered = (
                    _recover_absolute_reminder(execution_id, args)
                    if name == "reminder_create_absolute"
                    else _recover_reminder(execution_id, args)
                )

                if recovered is not None:
                    response = {
                        "success": True,
                        "action": "reminder_created",
                        "reminder": recovered,
                    }
                    with _ledger_connect() as db:
                        db.execute(
                            """
                            UPDATE tool_executions
                            SET status = 'completed',
                                result_json = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE execution_id = ?
                            """,
                            (
                                json.dumps(response, ensure_ascii=False),
                                execution_id,
                            ),
                        )
                    return response

                with _ledger_connect() as db:
                    db.execute(
                        """
                        UPDATE tool_executions
                        SET status = 'uncertain',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE execution_id = ?
                        """,
                        (execution_id,),
                    )
                raise RuntimeError(
                    "Reminder outcome uncertain; check before retrying"
                )

            # Preserve existing behavior for non-reminder tools.
            with _ledger_connect() as db:
                db.execute(
                    """
                    UPDATE tool_executions
                    SET status = 'failed',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE execution_id = ?
                    """,
                    (execution_id,),
                )
            raise

        with _ledger_connect() as db:
            db.execute(
                """
                UPDATE tool_executions
                SET status = 'completed',
                    result_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE execution_id = ?
                """,
                (
                    json.dumps(response, ensure_ascii=False),
                    execution_id,
                ),
            )

        return response
