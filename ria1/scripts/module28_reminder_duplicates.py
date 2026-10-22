"""RIA: read-only detection of equivalent pending reminders."""

from ria1.scripts.module8_command_executor import request_reminders


def normalize_title(title):
    if not isinstance(title, str):
        raise ValueError("Invalid reminder title")

    normalized = " ".join(title.split()).casefold()

    if not normalized:
        raise ValueError("Empty reminder title")

    return normalized


def find_duplicate_reminders(title, due_at):
    """Find pending reminders with identical titles and timestamps.

    This function never creates, modifies, or cancels reminders.
    """
    target_title = normalize_title(title)

    if type(due_at) is not int or due_at <= 0:
        raise ValueError("Invalid reminder timestamp")

    reminders = request_reminders("GET", "/reminders")

    if not isinstance(reminders, list):
        raise ValueError("Invalid reminder API response")

    duplicates = []

    for reminder in reminders:
        if not isinstance(reminder, dict):
            raise ValueError("Invalid reminder record")

        if reminder.get("status") != "pending":
            continue

        existing_title = reminder.get("title")
        existing_due_at = reminder.get("due_at")

        if not isinstance(existing_title, str):
            raise ValueError("Invalid saved reminder title")

        if type(existing_due_at) is not int:
            raise ValueError("Invalid saved reminder timestamp")

        if (
            normalize_title(existing_title) == target_title
            and existing_due_at == due_at
        ):
            duplicates.append(reminder)

    return duplicates
