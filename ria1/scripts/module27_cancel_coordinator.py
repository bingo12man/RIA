"""RIA P1.10.8.17 — session-bound confirmation coordinator."""

import json
import subprocess

from ria1.scripts.module15_tool_executor import OWNER
from ria1.scripts.module15_agent_bridge import ROOT

BACKEND_PYTHON = ROOT / ".venv" / "bin" / "python"

from ria1.scripts.module22_reminder_confirmations import (
    get_pending_cancellation,
    discard_pending_cancellation,
    reserve_cancellation,
)
from ria1.scripts.module26_cancel_executor import (
    execute_confirmed_cancellation,
)


def interpret_confirmation(message, proposal):
    """LLM interpretation only, without side effects."""
    payload = {
        "message": message,
        "proposal": {
            "reminder_id": proposal["reminder_id"],
            "title": proposal["title"],
            "due_at": proposal["due_at"],
        },
    }

    process = subprocess.run(
        [
            str(BACKEND_PYTHON),
            "-m",
            "ria1.scripts.module25_cancel_confirmation_runner",
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        timeout=35,
        check=False,
    )

    if process.returncode:
        raise RuntimeError(
            "Confirmation interpreter unavailable: "
            + process.stderr[-300:]
        )

    decision = json.loads(process.stdout)

    if (
        not isinstance(decision, dict)
        or set(decision) != {"decision", "reply"}
        or decision["decision"] not in {
            "confirm", "decline", "clarify", "unrelated"
        }
        or not isinstance(decision["reply"], str)
    ):
        raise ValueError("Invalid confirmation decision")

    if decision["decision"] == "clarify":
        if not decision["reply"].strip():
            raise ValueError("Missing clarification")
    elif decision["reply"]:
        raise ValueError("Unexpected confirmation reply")

    return decision


def handle_pending_confirmation(
    message,
    session_id,
    request_id,
    user_id=OWNER,
    interpreter=None,
    executor=None,
):
    """Return None for unrelated speech; otherwise process confirmation.

    The caller must provide a validated session and stable request ID.
    """

    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    proposal = get_pending_cancellation(session_id, user_id)

    if proposal is None:
        return None

    decide = interpreter or interpret_confirmation
    decision = decide(message, proposal)
    kind = decision["decision"]

    if kind == "unrelated":
        # Abandon the old proposal when the conversation changes subject.
        # A later unrelated "Yes" must not authorize stale cancellation.
        discard_pending_cancellation(session_id, user_id)
        return None

    if kind == "clarify":
        return {
            "action": "clarify",
            "success": False,
            "reply": decision["reply"].strip(),
        }

    if kind == "decline":
        discard_pending_cancellation(session_id, user_id)
        return {
            "action": "respond",
            "success": True,
            "reply": "Okay, I'll keep that reminder.",
        }

    # The gateway's request identity is bound to the reservation.
    # It is not derived from the reminder title or the model's reply.
    reserve_cancellation(session_id, request_id, user_id)

    execute = executor or execute_confirmed_cancellation
    return execute(session_id, request_id, user_id)
