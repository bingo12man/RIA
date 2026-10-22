import json
import re
import os
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "reminders.sqlite3"
DB_PATH = Path(os.environ.get("RIA_REMINDER_DB", str(DEFAULT_DB)))

app = FastAPI(title="RIA Reminder API")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL
            )
        """)


class NewReminder(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    minutes_from_now: int | None = Field(
        default=None, ge=0, le=525600
    )
    due_at: int | None = Field(default=None, ge=1)
    duplicate_of_id: int | None = Field(default=None, ge=1)
    request_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class SnoozeRequest(BaseModel):
    minutes: int = Field(default=5, ge=1, le=1440)


initialize()


@app.get("/health")
def health():
    return {"status": "ok"}


# RIA_P182_IDEMPOTENT_REMINDERS
# RIA_P11071_ABSOLUTE_REMINDERS
@app.post("/reminders")
def create_reminder(data: NewReminder):
    title = data.title.strip()

    if not title:
        raise HTTPException(422, "Reminder title cannot be blank")

    if (data.minutes_from_now is None) == (data.due_at is None):
        raise HTTPException(
            422,
            "Supply exactly one of minutes_from_now or due_at",
        )

    now = int(time.time())

    # Preserve the historical idempotency table.
    # -1 marks absolute-time requests.
    stored_minutes = (
        data.minutes_from_now
        if data.due_at is None
        else -1
    )

    requested_due_at = data.due_at

    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_requests (
                request_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                minutes_from_now INTEGER NOT NULL,
                reminder_id INTEGER NOT NULL UNIQUE,
                created_at INTEGER NOT NULL
            )
        """)

        # Migration runs before the write transaction.
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(reminder_requests)"
            )
        }

        if "requested_due_at" not in columns:
            conn.execute(
                "ALTER TABLE reminder_requests "
                "ADD COLUMN requested_due_at INTEGER"
            )

        # RIA_P110857_ATOMIC_DUPLICATE
        if "duplicate_of_id" not in columns:
            conn.execute(
                "ALTER TABLE reminder_requests "
                "ADD COLUMN duplicate_of_id INTEGER"
            )

        conn.execute("BEGIN IMMEDIATE")

        if data.request_id is not None:
            previous = conn.execute(
                """
                SELECT title, minutes_from_now,
                       requested_due_at, duplicate_of_id, reminder_id
                FROM reminder_requests
                WHERE request_id = ?
                """,
                (data.request_id,),
            ).fetchone()

            if previous is not None:
                if (
                    previous["title"] != title
                    or previous["minutes_from_now"] != stored_minutes
                    or previous["requested_due_at"] != requested_due_at
                    or previous["duplicate_of_id"] != data.duplicate_of_id
                ):
                    raise HTTPException(
                        409,
                        "Request ID reused with different reminder details",
                    )

                reminder = conn.execute(
                    "SELECT * FROM reminders WHERE id = ?",
                    (previous["reminder_id"],),
                ).fetchone()

                if reminder is None:
                    raise HTTPException(
                        409,
                        "Previously created reminder no longer exists",
                    )

                return dict(reminder)

        if requested_due_at is not None:
            if type(requested_due_at) is not int:
                raise HTTPException(422, "Invalid timestamp")

            if not now < requested_due_at <= now + 365 * 86400:
                raise HTTPException(
                    422,
                    "Absolute reminder must be in the future "
                    "and within 365 days",
                )

            due_at = requested_due_at
        else:
            due_at = now + stored_minutes * 60

        # RIA_P110857_ATOMIC_DUPLICATE
        if data.duplicate_of_id is not None:
            if requested_due_at is None:
                raise HTTPException(
                    422, "Duplicate creation requires absolute time"
                )

            original = conn.execute(
                """
                SELECT id, title, due_at, status
                FROM reminders
                WHERE id = ?
                """,
                (data.duplicate_of_id,),
            ).fetchone()

            normalize = lambda value: " ".join(
                value.split()
            ).casefold()

            if (
                original is None
                or original["status"] != "pending"
                or original["due_at"] != due_at
                or normalize(original["title"]) != normalize(title)
            ):
                raise HTTPException(
                    409,
                    "Original pending reminder no longer matches",
                )

        cursor = conn.execute(
            """
            INSERT INTO reminders
            (title, due_at, status, created_at)
            VALUES (?, ?, 'pending', ?)
            """,
            (title, due_at, now),
        )

        reminder_id = cursor.lastrowid

        if data.request_id is not None:
            conn.execute(
                """
                INSERT INTO reminder_requests
                (request_id, title, minutes_from_now,
                 reminder_id, created_at, requested_due_at,
                 duplicate_of_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.request_id,
                    title,
                    stored_minutes,
                    reminder_id,
                    now,
                    requested_due_at,
                    data.duplicate_of_id,
                ),
            )

    return {
        "id": reminder_id,
        "title": title,
        "due_at": due_at,
        "status": "pending",
    }


@app.get("/reminders")
def list_reminders():
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders ORDER BY due_at, id"
        ).fetchall()
    return [dict(row) for row in rows]


# RIA_P184_REMINDER_RECOVERY
@app.get("/reminders/by-request/{request_id}")
def get_reminder_by_request(request_id: str):
    """Look up an existing idempotent reminder without creating it."""
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_id):
        raise HTTPException(422, "Invalid request ID")

    with connect() as conn:
        # The table is created by the P1.8.2 reminder endpoint.
        table = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'reminder_requests'
            """
        ).fetchone()

        if table is None:
            raise HTTPException(404, "Reminder request not found")

        previous = conn.execute(
            """
            SELECT reminder_id FROM reminder_requests
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if previous is None:
            raise HTTPException(404, "Reminder request not found")

        reminder = conn.execute(
            "SELECT * FROM reminders WHERE id = ?",
            (previous["reminder_id"],),
        ).fetchone()

        if reminder is None:
            raise HTTPException(
                409,
                "Reminder request exists but reminder is missing",
            )

        return dict(reminder)



# RIA_P110814_CANCEL_RECOVERY
@app.get("/reminders/cancellations/by-request/{request_id}")
def get_cancellation_by_request(request_id: str):
    """Read a completed cancellation. Never retry a write."""
    import json
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_id):
        raise HTTPException(422, "Invalid cancellation request ID")

    with connect() as conn:
        exists = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table'
              AND name = 'reminder_cancellations'
            """
        ).fetchone()

        if exists is None:
            raise HTTPException(404, "Cancellation not found")

        row = conn.execute(
            """
            SELECT reminder_id, result_json,
                   expected_title, expected_due_at
            FROM reminder_cancellations
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(404, "Cancellation not found")

        reminder = conn.execute(
            "SELECT * FROM reminders WHERE id = ?",
            (row["reminder_id"],),
        ).fetchone()

        if reminder is None:
            raise HTTPException(409, "Cancelled reminder missing")

        if (
            row["expected_title"] is None
            or row["expected_due_at"] is None
            or reminder["title"] != row["expected_title"]
            or reminder["status"] != "cancelled"
        ):
            raise HTTPException(
                409, "Cancellation record verification failed"
            )

        result = json.loads(row["result_json"])

        if (
            not isinstance(result, dict)
            or result.get("id") != row["reminder_id"]
            or result.get("title") != row["expected_title"]
            or result.get("due_at") != row["expected_due_at"]
            or result.get("status") != "cancelled"
        ):
            raise HTTPException(
                409, "Cancellation result verification failed"
            )

        return {
            "request_id": request_id,
            "reminder_id": row["reminder_id"],
            "expected_title": row["expected_title"],
            "expected_due_at": row["expected_due_at"],
            "result": result,
        }


@app.get("/reminders/due")
def due_reminders():
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM reminders
               WHERE status = 'pending' AND due_at <= ?
               ORDER BY due_at, id""",
            (int(time.time()),),
        ).fetchall()
    return [dict(row) for row in rows]


def change_status(reminder_id, action):
    with connect() as conn:
        cursor = conn.execute(
            """UPDATE reminders SET status = ?
               WHERE id = ? AND status = 'pending'""",
            (action, reminder_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                404, "Pending reminder not found"
            )
    return {"id": reminder_id, "status": action}


@app.post("/reminders/{reminder_id}/done")
def mark_done(reminder_id: int):
    return change_status(reminder_id, "done")


@app.post("/reminders/{reminder_id}/skip")
def mark_skipped(reminder_id: int):
    return change_status(reminder_id, "skipped")


@app.post("/reminders/{reminder_id}/snooze")
def snooze(reminder_id: int, data: SnoozeRequest):
    new_due = int(time.time()) + data.minutes * 60

    with connect() as conn:
        cursor = conn.execute(
            """UPDATE reminders SET due_at = ?
               WHERE id = ? AND status = 'pending'""",
            (new_due, reminder_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                404, "Pending reminder not found"
            )

    return {
        "id": reminder_id,
        "status": "pending",
        "due_at": new_due,
    }




# RIA_P111_SAFE_ACTIONS
# Agent-facing done, skip and reschedule operations.
# Existing reminder endpoints remain unchanged.

class SafeReminderAction(BaseModel):
    request_id: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    expected_title: str = Field(min_length=1, max_length=200)
    expected_due_at: int = Field(ge=1)
    action: str = Field(pattern=r"^(done|skip|reschedule)$")
    due_at: int | None = Field(default=None, ge=1)


@app.post("/reminders/{reminder_id}/action-safe")
def reminder_action_safe(
    reminder_id: int,
    data: SafeReminderAction,
):
    if reminder_id < 1:
        raise HTTPException(422, "Invalid reminder ID")

    title = data.expected_title.strip()
    if not title:
        raise HTTPException(422, "Invalid title")

    if data.action == "reschedule":
        if data.due_at is None:
            raise HTTPException(422, "Reschedule needs a date and time")
    elif data.due_at is not None:
        raise HTTPException(422, "Unexpected reschedule time")

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_safe_actions (
                request_id TEXT PRIMARY KEY,
                reminder_id INTEGER NOT NULL,
                expected_title TEXT NOT NULL,
                expected_due_at INTEGER NOT NULL,
                action TEXT NOT NULL,
                requested_due_at INTEGER,
                result_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

        previous = conn.execute(
            "SELECT * FROM reminder_safe_actions WHERE request_id=?",
            (data.request_id,),
        ).fetchone()

        if previous is not None:
            if (
                previous["reminder_id"] != reminder_id
                or previous["expected_title"] != title
                or previous["expected_due_at"] != data.expected_due_at
                or previous["action"] != data.action
                or previous["requested_due_at"] != data.due_at
            ):
                raise HTTPException(
                    409, "Request ID already used for another action"
                )

            return json.loads(previous["result_json"])

        now = int(time.time())

        if data.action == "reschedule" and not (
            now < data.due_at <= now + 365 * 86400
        ):
            raise HTTPException(
                422, "Reschedule time must be in the future"
            )

        reminder = conn.execute(
            """
            SELECT id, title, due_at, status
            FROM reminders
            WHERE id=?
            """,
            (reminder_id,),
        ).fetchone()

        if (
            reminder is None
            or reminder["status"] != "pending"
            or reminder["title"] != title
            or reminder["due_at"] != data.expected_due_at
        ):
            raise HTTPException(
                409, "Reminder missing, changed or no longer pending"
            )

        new_status = {
            "done": "done",
            "skip": "skipped",
            "reschedule": "pending",
        }[data.action]

        new_due = (
            data.due_at
            if data.action == "reschedule"
            else data.expected_due_at
        )

        cursor = conn.execute(
            """
            UPDATE reminders
            SET status=?, due_at=?
            WHERE id=? AND status='pending'
              AND title=? AND due_at=?
            """,
            (
                new_status, new_due,
                reminder_id, title, data.expected_due_at,
            ),
        )

        if cursor.rowcount != 1:
            raise HTTPException(409, "Reminder changed during update")

        result = {
            "request_id": data.request_id,
            "action": data.action,
            "reminder": {
                "id": reminder_id,
                "title": title,
                "due_at": new_due,
                "status": new_status,
            },
        }

        conn.execute(
            """
            INSERT INTO reminder_safe_actions (
                request_id, reminder_id,
                expected_title, expected_due_at,
                action, requested_due_at,
                result_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.request_id, reminder_id,
                title, data.expected_due_at,
                data.action, data.due_at,
                json.dumps(result), now,
            ),
        )

    return result


@app.get("/reminders/actions/by-request/{request_id}")
def reminder_action_by_request(request_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_id):
        raise HTTPException(422, "Invalid request ID")

    with connect() as conn:
        exists = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='reminder_safe_actions'
            """
        ).fetchone()

        if exists is None:
            raise HTTPException(404, "Action not found")

        row = conn.execute(
            "SELECT result_json FROM reminder_safe_actions "
            "WHERE request_id=?",
            (request_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(404, "Action not found")

    return json.loads(row["result_json"])


# RIA_P110866_SAFE_SNOOZE
# Agent-facing endpoint. Legacy /snooze remains unchanged.
class SafeSnoozeRequest(BaseModel):
    request_id: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    expected_title: str = Field(min_length=1, max_length=200)
    expected_due_at: int = Field(ge=1)
    minutes: int | None = Field(default=None, ge=1, le=525600)
    due_at: int | None = Field(default=None, ge=1)


@app.post("/reminders/{reminder_id}/snooze-safe")
def snooze_safe(reminder_id: int, data: SafeSnoozeRequest):
    if reminder_id < 1:
        raise HTTPException(422, "Invalid reminder ID")

    if (data.minutes is None) == (data.due_at is None):
        raise HTTPException(
            422, "Specify exactly one snooze time"
        )

    title = data.expected_title.strip()
    if not title:
        raise HTTPException(422, "Invalid title")

    now = int(time.time())
    new_due = (
        now + data.minutes * 60
        if data.minutes is not None
        else data.due_at
    )

    if not now < new_due <= now + 365 * 86400:
        raise HTTPException(422, "Snooze time out of range")

    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_safe_snoozes (
                request_id TEXT PRIMARY KEY,
                reminder_id INTEGER NOT NULL,
                expected_title TEXT NOT NULL,
                expected_due_at INTEGER NOT NULL,
                minutes INTEGER,
                requested_due_at INTEGER,
                result_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

        conn.execute("BEGIN IMMEDIATE")

        previous = conn.execute(
            "SELECT * FROM reminder_safe_snoozes "
            "WHERE request_id=?",
            (data.request_id,),
        ).fetchone()

        if previous is not None:
            if (
                previous["reminder_id"] != reminder_id
                or previous["expected_title"] != title
                or previous["expected_due_at"] != data.expected_due_at
                or previous["minutes"] != data.minutes
                or previous["requested_due_at"] != data.due_at
            ):
                raise HTTPException(
                    409, "Request ID reused with different snooze"
                )
            return json.loads(previous["result_json"])

        current = conn.execute(
            "SELECT id, title, due_at, status FROM reminders "
            "WHERE id=?",
            (reminder_id,),
        ).fetchone()

        if (
            current is None
            or current["status"] != "pending"
            or current["title"] != title
            or current["due_at"] != data.expected_due_at
        ):
            raise HTTPException(
                409, "Reminder changed or is no longer pending"
            )

        result = {
            "id": reminder_id,
            "title": title,
            "status": "pending",
            "due_at": new_due,
        }

        conn.execute(
            "UPDATE reminders SET due_at=? "
            "WHERE id=? AND status='pending'",
            (new_due, reminder_id),
        )

        conn.execute(
            """
            INSERT INTO reminder_safe_snoozes (
                request_id, reminder_id, expected_title,
                expected_due_at, minutes, requested_due_at,
                result_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.request_id, reminder_id, title,
                data.expected_due_at, data.minutes, data.due_at,
                json.dumps(result), now,
            ),
        )

    return result


@app.get("/reminders/snoozes/by-request/{request_id}")
def get_safe_snooze_by_request(request_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_id):
        raise HTTPException(422, "Invalid request ID")

    with connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM reminder_safe_snoozes "
            "WHERE request_id=?",
            (request_id,),
        ).fetchone() if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='reminder_safe_snoozes'"
        ).fetchone() else None

    if row is None:
        raise HTTPException(404, "Snooze request not found")

    return json.loads(row["result_json"])


# RIA_P11081_SAFE_CANCELLATION
class CancelReminderRequest(BaseModel):
    request_id: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    expected_title: str = Field(min_length=1, max_length=200)
    expected_due_at: int = Field(ge=1)


@app.get("/reminders/{reminder_id}")
def get_reminder(reminder_id: int):
    if reminder_id < 1:
        raise HTTPException(422, "Invalid reminder ID")

    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?",
            (reminder_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(404, "Reminder not found")

    return dict(row)


@app.post("/reminders/{reminder_id}/cancel")
def cancel_reminder(reminder_id: int, data: CancelReminderRequest):
    """Idempotent soft cancellation of one exact pending reminder."""
    if reminder_id < 1:
        raise HTTPException(422, "Invalid reminder ID")

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_cancellations (
                request_id TEXT PRIMARY KEY,
                reminder_id INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expected_title TEXT,
                expected_due_at INTEGER
            )
        """)

        # RIA_P110813_STRICT_REPLAY
        # Support databases created before snapshot binding.
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(reminder_cancellations)"
            )
        }
        if "expected_title" not in columns:
            conn.execute(
                "ALTER TABLE reminder_cancellations "
                "ADD COLUMN expected_title TEXT"
            )
        if "expected_due_at" not in columns:
            conn.execute(
                "ALTER TABLE reminder_cancellations "
                "ADD COLUMN expected_due_at INTEGER"
            )

        previous = conn.execute(
            """
            SELECT reminder_id, result_json,
                   expected_title, expected_due_at
            FROM reminder_cancellations
            WHERE request_id = ?
            """,
            (data.request_id,),
        ).fetchone()

        if previous is not None:
            if (
                previous["reminder_id"] != reminder_id
                or previous["expected_title"] != data.expected_title
                or previous["expected_due_at"] != data.expected_due_at
            ):
                raise HTTPException(
                    409,
                    "Cancellation request ID reused with different details",
                )

            import json
            return json.loads(previous["result_json"])

        reminder = conn.execute(
            "SELECT * FROM reminders WHERE id = ?",
            (reminder_id,),
        ).fetchone()

        if reminder is None:
            raise HTTPException(404, "Reminder not found")

        # RIA_P110812_SNAPSHOT_GUARD
        if (
            reminder["title"] != data.expected_title
            or reminder["due_at"] != data.expected_due_at
        ):
            raise HTTPException(
                409,
                "Reminder details changed since confirmation",
            )

        if reminder["status"] != "pending":
            raise HTTPException(
                409,
                "Only pending reminders can be cancelled",
            )

        cursor = conn.execute(
            """
            UPDATE reminders
            SET status = 'cancelled'
            WHERE id = ?
              AND status = 'pending'
              AND title = ?
              AND due_at = ?
            """,
            (
                reminder_id,
                data.expected_title,
                data.expected_due_at,
            ),
        )

        if cursor.rowcount != 1:
            raise HTTPException(
                409,
                "Reminder state changed during cancellation",
            )

        result = {
            "id": reminder_id,
            "title": reminder["title"],
            "due_at": reminder["due_at"],
            "status": "cancelled",
        }

        import json
        conn.execute(
            """
            INSERT INTO reminder_cancellations
            (request_id, reminder_id, result_json, created_at,
             expected_title, expected_due_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                data.request_id,
                reminder_id,
                json.dumps(result),
                int(time.time()),
                data.expected_title,
                data.expected_due_at,
            ),
        )

        return result
