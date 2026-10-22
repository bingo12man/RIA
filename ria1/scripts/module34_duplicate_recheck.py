"""Recheck an existing reminder before approved duplicate creation.

Read-only: this module never creates or changes reminders.
"""

import json

from ria1.scripts.module21_absolute_time import validate_scheduled_time
from ria1.scripts.module28_reminder_duplicates import (
    find_duplicate_reminders,
)


def recheck_duplicate(tool_name, args):
    if tool_name != "reminder_create_absolute":
        raise PermissionError(
            "Duplicate recheck supports absolute reminders only"
        )

    if not isinstance(args, dict):
        raise ValueError("Invalid reminder arguments")

    due_at = validate_scheduled_time(
        args["scheduled_at"],
        args["timezone"],
    )

    matches = find_duplicate_reminders(
        args["title"],
        due_at,
    )

    if not matches:
        raise PermissionError(
            "Original duplicate reminder no longer exists"
        )

    return {
        "verified": True,
        "due_at": due_at,
        "matching_reminder_ids": [
            row["id"] for row in matches
        ],
    }
