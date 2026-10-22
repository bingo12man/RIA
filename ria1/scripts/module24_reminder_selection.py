"""RIA P1.10.8.4: validated, read-only reminder selection."""

import json
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

from ria1.scripts.module15_agent_bridge import ROOT

# Cancellation LLM selector uses the backend Python environment.
BACKEND_PYTHON = ROOT / ".venv" / "bin" / "python"

from ria1.scripts.module15_tool_executor import OWNER
from ria1.scripts.module20_native_sessions import get_history
from ria1.scripts.module22_reminder_confirmations import stage_cancellation
from ria1.scripts.module23_reminder_discovery import (
    list_pending_reminders,
    validate_selected_reminder,
)


def model_select(message, candidates, history=None):
    process = subprocess.run(
        [
            str(BACKEND_PYTHON),
            "-m",
            "ria1.scripts.module24_reminder_selection_runner",
        ],
        input=json.dumps({
            "message": message,
            "candidates": candidates,
            "history": history if history is not None else [],
        }),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        timeout=30,
        check=False,
    )

    if process.returncode:
        raise RuntimeError(
            "Reminder selection model unavailable: "
            + process.stderr[-300:]
        )

    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid model response") from exc

    return result


def _validate_decision(decision, candidates):
    if not isinstance(decision, dict) or set(decision) != {
        "decision", "reminder_id", "reply"
    }:
        raise ValueError("Invalid selection structure")

    kind = decision["decision"]
    reminder_id = decision["reminder_id"]
    reply = decision["reply"]

    if kind not in {"select", "clarify", "respond"}:
        raise ValueError("Unsupported selection decision")

    if not isinstance(reply, str):
        raise ValueError("Invalid selection reply")

    if kind == "select":
        if reply:
            raise ValueError("Selection must not claim completion")

        return validate_selected_reminder(reminder_id, candidates)

    if reminder_id is not None or not reply.strip():
        raise ValueError("Invalid non-selection decision")

    return None


def select_cancellation_candidate(
    message,
    session_id,
    user_id=OWNER,
    selector=None,
    history=None,
):
    """Select and stage one exact reminder; never cancel it."""

    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    if not isinstance(message, str) or not 0 < len(message.strip()) <= 4000:
        raise ValueError("Invalid message")

    # Validates ownership and expiry of the conversation.
    get_history(session_id, user_id)

    candidates = list_pending_reminders()

    if history is None:
        history = get_history(session_id, user_id)

    if selector is None:
        decision = model_select(message, candidates, history=history)
    else:
        # Preserve existing two-argument injected test selectors.
        decision = selector(message, candidates)
    selected = _validate_decision(decision, candidates)

    if selected is None:
        return {
            "action": decision["decision"],
            "success": False,
            "reply": decision["reply"].strip(),
            "session_id": session_id,
        }

    # The confirmation module independently reads the reminder again
    # and checks that it is still pending.
    proposal = stage_cancellation(
        session_id,
        selected["id"],
        user_id,
    )

    local = datetime.fromtimestamp(
        proposal["due_at"],
        ZoneInfo("Asia/Kolkata"),
    )

    date_text = local.strftime("%A, %B %d at %I:%M %p")
    date_text = date_text.replace(" 0", " ").replace(" at 0", " at ")

    return {
        "action": "cancel_confirmation_required",
        "success": False,
        "reply": (
            f"I found your {proposal['title']} reminder for "
            f"{date_text}. Are you sure you want to cancel it?"
        ),
        "session_id": session_id,
        "reminder_id": proposal["reminder_id"],
    }
