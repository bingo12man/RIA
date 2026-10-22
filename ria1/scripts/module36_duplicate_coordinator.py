"""RIA duplicate-reminder gateway coordinator."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ria1.scripts.module21_absolute_time import validate_scheduled_time
from ria1.scripts.module28_reminder_duplicates import find_duplicate_reminders
from ria1.scripts.module30_duplicate_proposals import (
    stage_duplicate,
    get_pending_duplicate,
    discard_duplicate,
    reserve_duplicate,
)
from ria1.scripts.module31_duplicate_executor import execute_approved_duplicate


def classify_duplicate_reply(message, proposal):
    backend = Path(__file__).resolve().parents[2]
    python = backend / ".venv" / "bin" / "python"
    # Run as a module so Python resolves the ria1 package.

    result = subprocess.run(
        [
            str(python),
            "-m",
            "ria1.scripts.module35_duplicate_confirmation_cli",
        ],
        input=json.dumps({
            "message": message,
            "proposal": proposal,
        }),
        text=True,
        capture_output=True,
        timeout=30,
        cwd=str(backend),
        check=True,
    )

    parsed = json.loads(result.stdout)
    if not isinstance(parsed, dict) or set(parsed) != {"decision"}:
        raise ValueError("Invalid confirmation result")

    decision = parsed["decision"]
    if decision not in {"confirm", "decline", "clarify", "unrelated"}:
        raise ValueError("Invalid confirmation decision")
    return decision


def maybe_stage_duplicate(session_id, tool, args, request_id, user_id):
    # Preserve current relative-time creation behavior for now.
    if tool != "reminder_create_absolute":
        return None

    due_at = validate_scheduled_time(
        args["scheduled_at"], args["timezone"]
    )

    matches = find_duplicate_reminders(args["title"], due_at)
    if not matches:
        return None

    # Fail closed if an old proposal already exists in this session.
    existing = get_pending_duplicate(session_id, user_id)
    if existing is not None:
        raise PermissionError("Another duplicate approval is pending")

    original_id = matches[0].get("id")
    if type(original_id) is not int or original_id <= 0:
        raise ValueError("Invalid original reminder identity")

    stage_duplicate(
        session_id, tool, args, request_id, user_id,
        original_reminder_id=original_id,
    )

    date_text = datetime.fromtimestamp(
        due_at, ZoneInfo(args["timezone"])
    ).strftime("%d %b at %I:%M %p")

    title = args["title"].strip()

    return {
        "action": "duplicate_confirmation_required",
        "success": False,
        "reply": (
            f"You already have a reminder for {title} "
            f"on {date_text}. Do you want another one?"
        ),
    }


def handle_duplicate_confirmation(
    message, session_id, request_id, user_id
):
    pending = get_pending_duplicate(session_id, user_id)
    if pending is None:
        return None

    args = pending["arguments"]
    if pending["tool_name"] != "reminder_create_absolute":
        raise PermissionError("Unsupported duplicate proposal")

    due_at = validate_scheduled_time(
        args["scheduled_at"], args["timezone"]
    )

    decision = classify_duplicate_reply(
        message,
        {"title": args["title"], "due_at": due_at},
    )

    if decision == "unrelated":
        discard_duplicate(session_id, user_id)
        return None

    if decision == "decline":
        discard_duplicate(session_id, user_id)
        return {
            "action": "respond",
            "success": True,
            "reply": "Okay, I'll keep your existing reminder.",
        }

    if decision == "clarify":
        return {
            "action": "clarify",
            "success": False,
            "reply": "Do you want another reminder, or just the existing one?",
        }

    reserve_duplicate(session_id, request_id, user_id)

    # The executor performs both duplicate rechecks and the durable
    # execution claim. Replays must use read-only recovery.
    # RIA_P110848_DUPLICATE_SESSION_RESET
    result = execute_approved_duplicate(
        session_id, request_id, user_id
    )

    if (
        not isinstance(result, dict)
        or result.get("success") is not True
        or result.get("action") != "reminder_created"
        or not isinstance(result.get("reminder"), dict)
    ):
        raise RuntimeError("Unverified duplicate creation")

    # Preserve the durable claim and approval records for audit.
    # Close this session after the gateway persists the result.
    return {
        **result,
        "duplicate_confirmation_completed": True,
    }
