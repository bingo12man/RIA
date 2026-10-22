"""RIA P1.10.8.3 — Read-only reminder discovery.

No natural-language matching, cancellation or database mutation.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from ria1.scripts.module8_command_executor import request_reminders

MAX_REMINDERS = 100


def list_pending_reminders(timezone="Asia/Kolkata"):
    zone = ZoneInfo(timezone)

    reminders = request_reminders("GET", "/reminders")

    if not isinstance(reminders, list):
        raise ValueError("Unexpected reminder API response")

    if len(reminders) > MAX_REMINDERS:
        raise ValueError(
            "Too many reminders for safe selection; narrow the search"
        )

    results = []
    seen_ids = set()

    for item in reminders:
        if not isinstance(item, dict):
            raise ValueError("Invalid reminder record")

        reminder_id = item.get("id")
        title = item.get("title")
        due_at = item.get("due_at")
        status = item.get("status")

        if (
            type(reminder_id) is not int
            or reminder_id < 1
            or reminder_id in seen_ids
            or not isinstance(title, str)
            or not title.strip()
            or type(due_at) is not int
            or not isinstance(status, str)
        ):
            raise ValueError("Invalid reminder data")

        seen_ids.add(reminder_id)

        if status != "pending":
            continue

        local = datetime.fromtimestamp(due_at, zone)

        results.append({
            "id": reminder_id,
            "title": title,
            "due_at": due_at,
            "local_datetime": local.isoformat(
                timespec="seconds"
            ),
            "timezone": timezone,
        })

    return sorted(
        results,
        key=lambda reminder: (
            reminder["due_at"],
            reminder["id"],
        ),
    )


def validate_selected_reminder(reminder_id, candidates):
    """The selected ID must match exactly one known candidate."""

    if type(reminder_id) is not int or reminder_id < 1:
        raise ValueError("Invalid selected reminder ID")

    matches = [
        item for item in candidates
        if item["id"] == reminder_id
    ]

    if len(matches) != 1:
        raise ValueError(
            "Selected reminder is not in the candidate list"
        )

    return matches[0]
