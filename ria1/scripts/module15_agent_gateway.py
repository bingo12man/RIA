"""RIA P1.6.2: conservative agent-to-tool gateway.

Not connected to the live voice API.
"""

import re

from ria1.scripts.module15_agent_bridge import select_agent_action
from ria1.scripts.module15_tool_executor import execute_tool, OWNER


def _words(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def authorize_tool(message, name, args):
    """Reject unsupported or insufficiently explicit actions.

    This is a temporary, conservative intent guard, not a
    complete semantic authorization system.
    """
    if not isinstance(message, str) or not isinstance(args, dict):
        return False

    words = _words(message)

    if name == "memory_list":
        return (
            "remember" in words
            or "memories" in words
            or "know" in words
        ) and not bool(
            words & {"forget", "delete", "remove", "change", "update"}
        )

    if name == "memory_save":
        return bool(words & {"remember", "memorize", "save"}) and (
            "fact" in args
        ) and not bool(words & {"forget", "delete"})

    if name == "memory_update":
        return bool(words & {"change", "update", "correct", "replace"}) and (
            "old_fact" in args and "new_fact" in args
        )

    if name == "memory_forget":
        return bool(words & {"forget", "delete", "remove"}) and (
            "exact_fact" in args
        ) and not bool(words & {"everything", "all"})

    if name == "reminder_create":
        return bool(words & {"remind", "reminder"}) and (
            "title" in args and "minutes_from_now" in args
        )

    return False


def run_agent_request(message, request_id, user_id=OWNER, selector=None):
    """Select and optionally execute one explicitly authorized tool.

    A no-tool reply does not create any side effects.
    """
    if user_id != OWNER:
        raise PermissionError("Unauthorized RIA profile")

    if not isinstance(message, str) or not message.strip():
        raise ValueError("Empty message")

    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    # RIA_P165_REQUEST_BINDING
    from ria1.scripts.module15_request_guard import bind_request
    bind_request(request_id, message, user_id)

    select = selector or select_agent_action
    selection = select(message)

    calls = selection.get("tool_calls")
    if not isinstance(calls, list):
        raise ValueError("Invalid agent tool-call response")

    if len(calls) > 1:
        return {
            "action": "clarification",
            "success": False,
            "reply": "Could you ask me to do one thing at a time?",
        }

    if not calls:
        return {
            "action": "conversation",
            "success": True,
            "reply": selection.get("reply", ""),
        }

    call = calls[0]
    name = call.get("name")
    args = call.get("arguments")

    if not authorize_tool(message, name, args):
        return {
            "action": "authorization_rejected",
            "success": False,
            "reply": (
                "I want to make sure I understood. "
                "Could you state the action you'd like me to take?"
            ),
        }

    # RIA_P163_ARGUMENT_GROUNDING
    from ria1.scripts.module15_argument_guard import grounded

    if not grounded(message, name, args):
        return {
            "action": "authorization_rejected",
            "success": False,
            "reply": (
                "I couldn't verify the details of that action. "
                "Could you say it a little more clearly?"
            ),
        }

    # Use the frontend interaction ID, not the model's tool-call ID.
    # RIA_P167_RESPONSE_INTEGRATION
    from ria1.scripts.module15_agent_response import (
        format_agent_result,
        uncertain_execution_response,
    )

    try:
        result = execute_tool(name, args, user_id, request_id)
    except (RuntimeError, TimeoutError, ConnectionError):
        return uncertain_execution_response()

    return format_agent_result(result)

    replies = {
        "memory_saved": "Got it! I'll remember that.",
        "memory_updated": "Done! I've updated that memory.",
        "memory_deleted": "Okay, I've forgotten that saved fact.",
        "memory_listed": "Here's what I have saved.",
        "reminder_created": "Done! Your reminder is scheduled.",
    }

    if result["action"] == "memory_listed":
        memories = list(result["memories"].values())
        reply = (
            "Here's what I remember: " + "; ".join(memories)
            if memories else "I don't have anything saved yet."
        )
    else:
        reply = replies.get(
            result["action"], "Your request was completed."
        )

    return {
        **result,
        "reply": reply,
    }
