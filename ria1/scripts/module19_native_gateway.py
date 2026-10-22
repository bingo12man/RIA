"""RIA P1.9.2 — LLM-native gateway, without language regex guards."""

import re

from ria1.scripts.module15_tool_executor import OWNER, execute_tool
from ria1.scripts.module15_request_guard import bind_request
from ria1.scripts.module15_agent_response import (
    format_agent_result,
    uncertain_execution_response,
)
from ria1.scripts.module19_decision_bridge import (
    select_native_decision,
)

ALLOWED_TOOLS = {
    "memory_save",
    "memory_list",
    "memory_update",
    "memory_forget",
    "reminder_create",
    "reminder_create_absolute",
    "reminder_cancel_lookup",
    "reminder_snooze_lookup",
    "reminder_manage_lookup",
    "reminder_list",
}


def _run_native_request_once(
    message,
    request_id,
    user_id=OWNER,
    selector=None,
    executor=None,
    session_id=None,
):
    """Make one LLM decision, then optionally execute one trusted tool."""

    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    if not isinstance(message, str) or not message.strip():
        raise ValueError("Empty message")

    if not isinstance(request_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,128}", request_id
    ):
        raise ValueError("Invalid request ID")

    # Bind this request ID to this exact instruction.
    bind_request(request_id, message, user_id)

    # The LLM handles intent, negation and ambiguity.
    # RIA_P1103_GATEWAY_SESSIONS
    from ria1.scripts.module20_native_sessions import get_history

    history = get_history(session_id, user_id)

    # RIA_P110817_CONFIRMATION_GATEWAY
    # Pending user confirmation takes priority over new tool selection.
    # Injected test selectors retain their existing behavior.
    if selector is None:
        from ria1.scripts.module27_cancel_coordinator import (
            handle_pending_confirmation,
        )

        confirmation_result = handle_pending_confirmation(
            message,
            session_id,
            request_id,
            user_id=user_id,
        )

        if confirmation_result is not None:
            return confirmation_result

        # RIA_P110844_DUPLICATE_PENDING
        from ria1.scripts.module36_duplicate_coordinator import (
            handle_duplicate_confirmation,
        )

        duplicate_result = handle_duplicate_confirmation(
            message, session_id, request_id, user_id
        )
        if duplicate_result is not None:
            return duplicate_result

        # RIA_P110867_SNOOZE_GATEWAY
        from ria1.scripts.module38_snooze_coordinator import (
            handle_snooze_followup,
        )

        snooze_result = handle_snooze_followup(
            message, session_id, request_id, user_id
        )
        if snooze_result is not None:
            return snooze_result

        decision = select_native_decision(message, history=history)
    else:
        # Preserve existing injected selector interface for tests.
        decision = selector(message)

    if not isinstance(decision, dict):
        raise ValueError("Invalid LLM decision")

    if set(decision) != {
        "decision", "tool", "arguments", "reply"
    }:
        raise ValueError("Invalid decision structure")

    kind = decision["decision"]
    tool = decision["tool"]
    args = decision["arguments"]
    reply = decision["reply"]

    if kind not in {"execute", "clarify", "respond", "reject"}:
        raise ValueError("Unsupported decision")

    if not isinstance(args, dict) or not isinstance(reply, str):
        raise ValueError("Invalid decision fields")

    # No execution, and no legacy parser fallback.
    if kind != "execute":
        if tool is not None or args or not reply.strip():
            raise ValueError("Invalid non-execution decision")

        return {
            "action": kind,
            "success": kind == "respond",
            "reply": reply.strip(),
        }

    # Deterministic execution safety, not language interpretation.
    if tool not in ALLOWED_TOOLS:
        raise PermissionError("Unsupported tool")

    if reply:
        raise ValueError("LLM must not confirm execution prematurely")

    # RIA_P110867_SNOOZE_GATEWAY
    if tool == "reminder_snooze_lookup":
        if args != {}:
            raise ValueError("Snooze lookup takes no arguments")

        if session_id is None:
            raise ValueError("Snooze requires an active session")

        from ria1.scripts.module38_snooze_coordinator import (
            begin_snooze,
        )

        return begin_snooze(
            message, session_id, request_id, user_id
        )

    # RIA_P111_MANAGE_GATEWAY
    if tool == "reminder_manage_lookup":
        if args != {}:
            raise ValueError("Manage lookup takes no arguments")

        if session_id is None:
            raise ValueError("Manage lookup requires a session")

        from ria1.scripts.module39_reminder_actions import (
            handle_reminder_action,
        )

        return handle_reminder_action(
            message, session_id, request_id, user_id
        )

    # RIA_REMINDER_LIST_V1
    if tool == "reminder_list":
        from datetime import date, datetime
        from ria1.scripts.module23_reminder_discovery import (
            list_pending_reminders,
        )

        if set(args) not in (set(), {"date"}):
            raise ValueError("Invalid reminder list arguments")

        requested_date = args.get("date")
        if requested_date is not None:
            if (
                not isinstance(requested_date, str)
                or len(requested_date) != 10
            ):
                raise ValueError("Invalid reminder date")

            parsed_date = date.fromisoformat(requested_date)
            if parsed_date.isoformat() != requested_date:
                raise ValueError("Invalid reminder date")

        reminders = list_pending_reminders()

        if requested_date is not None:
            reminders = [
                item for item in reminders
                if item["local_datetime"][:10] == requested_date
            ]

        if not reminders:
            spoken = (
                "You have no pending reminders for that date."
                if requested_date is not None
                else "You have no pending reminders."
            )
        else:
            lines = []
            for item in reminders[:5]:
                when = datetime.fromisoformat(
                    item["local_datetime"]
                )
                lines.append(
                    item["title"] + " on "
                    + when.strftime("%A, %B %d at %I:%M %p")
                )

            spoken = "Here are your reminders: " + "; ".join(lines)
            if len(reminders) > 5:
                spoken += (
                    f". You have {len(reminders) - 5} more. "
                    "Ask for a specific date to narrow the list."
                )

        return {
            "action": "reminder_listed",
            "success": True,
            "reply": spoken,
            "reminders": reminders,
        }

    # RIA_P11087_READ_ONLY_SELECTION
    # This action is handled before the trusted tool executor.
    if tool == "reminder_cancel_lookup":
        if args != {}:
            raise ValueError("Reminder lookup takes no arguments")

        if session_id is None:
            raise ValueError("Reminder lookup requires a session")

        from ria1.scripts.module24_reminder_selection import (
            select_cancellation_candidate,
        )

        return select_cancellation_candidate(
            message,
            session_id,
            user_id=user_id,
            history=history,
        )


    # RIA_M84_MEMORY_WRITE_GATE
    if tool in {"memory_save", "memory_update", "memory_forget"}:
        if not _memory_write_is_explicit(message, tool):
            return {
                "action": "clarify",
                "success": False,
                "reply": (
                    "I can follow that preference for now. "
                    "If you want to change what I remember, "
                    "please explicitly ask me to save, update, "
                    "or forget the memory."
                ),
            }

    # RIA_P110844_DUPLICATE_CREATION
    if selector is None and executor is None:
        from ria1.scripts.module36_duplicate_coordinator import (
            maybe_stage_duplicate,
        )
        duplicate_result = maybe_stage_duplicate(
            session_id, tool, args, request_id, user_id
        )
        if duplicate_result is not None:
            return duplicate_result

    execute = executor or execute_tool

    try:
        result = execute(tool, args, user_id, request_id)
    except (RuntimeError, TimeoutError, ConnectionError):
        return uncertain_execution_response()

    return format_agent_result(result, user_message=message)



# RIA_M84_EXPLICIT_MEMORY_AUTHORIZATION
def _memory_write_is_explicit(message, tool):
    """Conservative authorization for persistent memory mutations."""
    if tool not in {
        "memory_save",
        "memory_update",
        "memory_forget",
    }:
        return True

    if not isinstance(message, str):
        return False

    text = " ".join(
        message.casefold()
        .replace(",", " ")
        .replace("!", " ")
        .replace(".", " ")
        .split()
    )

    # Strip supported wake-word prefixes, not arbitrary content.
    for prefix in (
        "hey ria ",
        "hi ria ",
        "ria ",
        "hey rhea ",
        "hi rhea ",
        "rhea ",
        "please ",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):]

    if text.startswith("please "):
        text = text[len("please "):]

    if tool == "memory_save":
        prefixes = (
            "remember that ",
            "remember my preference ",
            "save to memory that ",
            "save this fact ",
            "save this preference ",
        )
    elif tool == "memory_update":
        prefixes = (
            "change my saved preference ",
            "update my saved preference ",
            "correct my saved preference ",
            "change my saved memory ",
            "update my saved memory ",
        )
    else:
        prefixes = (
            "forget that ",
            "forget my saved ",
            "forget my preference ",
            "delete my saved ",
            "remove my saved ",
        )

    return any(text.startswith(prefix) for prefix in prefixes)

# RIA_P194_DURABLE_NATIVE_REPLAY
# One request ID maps to one completed response.
# Unresolved requests are never executed again automatically.

import json
from ria1.scripts.module15_tool_executor import _ledger_connect


def run_native_request(
    message,
    request_id,
    user_id=OWNER,
    selector=None,
    executor=None,
    session_id=None,
):
    if user_id != OWNER:
        raise PermissionError("Unauthorized profile")

    # Validate and bind before checking replay.
    bind_request(request_id, message, user_id)

    from ria1.scripts.module20_native_sessions import (
        new_session, get_history, append_turn, delete_session,
    )

    with _ledger_connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS native_request_results (
                request_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT
            )
        """)

        db.execute("BEGIN IMMEDIATE")

        previous = db.execute(
            """
            SELECT user_id, status, result_json
            FROM native_request_results
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if previous is not None:
            if previous["user_id"] != user_id:
                raise PermissionError("Request owner mismatch")

            if previous["status"] == "completed":
                return json.loads(previous["result_json"])

            raise RuntimeError(
                "Previous native request is unresolved; "
                "do not automatically retry execution"
            )

        db.execute(
            """
            INSERT INTO native_request_results
            (request_id, user_id, status, result_json)
            VALUES (?, ?, 'pending', NULL)
            """,
            (request_id, user_id),
        )

    # Only the first attempt can create a conversation turn.
    # RIA_P1103_GATEWAY_SESSIONS
    active_session = session_id or new_session(user_id)
    get_history(active_session, user_id)

    result = _run_native_request_once(
        message,
        request_id,
        user_id=user_id,
        selector=selector,
        executor=executor,
        session_id=active_session,
    )

    if not isinstance(result, dict):
        raise ValueError("Invalid executor response")

    result = dict(result)

    changed_memory = (
        result.get("success") is True
        and result.get("action") in {
            "memory_saved",
            "memory_updated",
            "memory_deleted",
            "reminder_cancelled",
        }
    )

    # RIA_P110848_DUPLICATE_SESSION_RESET
    if result.get("duplicate_confirmation_completed") is True:
        changed_memory = True

    # Honor trusted coordinator completion signals.
    # Never reset on a mere clarification or failed action.
    if result.get("reset_session") is True:
        if result.get("success") is not True:
            raise ValueError("Invalid session reset request")
        changed_memory = True

    if changed_memory:
        delete_session(active_session, user_id)
        result["session_id"] = None
        result["reset_session"] = True
    else:
        reply = result.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Missing assistant response")

        append_turn(
            active_session,
            request_id,
            message,
            reply,
            user_id,
        )
        result["session_id"] = active_session

    with _ledger_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """
            UPDATE native_request_results
            SET status = 'completed', result_json = ?
            WHERE request_id = ?
              AND user_id = ?
              AND status = 'pending'
            """,
            (json.dumps(result), request_id, user_id),
        )

    return result
