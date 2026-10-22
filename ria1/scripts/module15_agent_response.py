
def _format_memories_naturally(memories):
    """Narrate saved facts without changing or inventing their meaning."""
    statements = []
    mentions = []
    seen = set()

    for value in memories.values():
        if not isinstance(value, str):
            continue

        fact = value.strip().rstrip(".!? ").strip()
        if not fact:
            continue

        normalized = " ".join(fact.casefold().split())
        if normalized in seen:
            continue
        seen.add(normalized)

        lowered = fact.casefold()

        if lowered.startswith("i "):
            statements.append("you " + fact[2:])

        elif lowered.startswith("my "):
            statements.append("your " + fact[3:])

        elif lowered.startswith("i'm "):
            statements.append("you're " + fact[4:])

        elif lowered.startswith("i’ve "):
            statements.append("you've " + fact[5:])

        elif lowered.startswith("you ") or lowered.startswith("your "):
            statements.append(fact[0].lower() + fact[1:])

        else:
            mentions.append(fact)

    def join_naturally(items):
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return items[0] + " and " + items[1]
        return ", ".join(items[:-1]) + ", and " + items[-1]

    if not statements and not mentions:
        return (
            "I don't have any saved memories about you yet. "
            "You can tell me what you'd like me to remember!"
        )

    sentences = []

    if statements:
        sentences.append(
            "I remember that " + join_naturally(statements) + "."
        )

    if mentions:
        sentences.append(
            "You've also mentioned " + join_naturally(mentions) + "."
        )

    return (
        "Of course! "
        + " ".join(sentences)
        + " That's what I know about you so far!"
    )


"""RIA P1.6.6: truthful, user-friendly agent responses."""


def format_agent_result(result, user_message=None):
    """Return a safe response without inventing action success."""
    if not isinstance(result, dict):
        raise ValueError("Invalid tool result")

    action = result.get("action")
    success = result.get("success") is True

    if not success:
        return {
            "action": "clarification",
            "success": False,
            "reply": (
                "I couldn't safely complete that request. "
                "Could you clarify what you'd like me to do?"
            ),
        }

    if action == "memory_saved":
        reply = "Got it! I'll remember that."

    elif action == "memory_updated":
        reply = "Done! I've updated that memory."

    elif action == "memory_deleted":
        reply = "Okay, I've forgotten that saved fact."

    elif action == "memory_listed":
        memories = result.get("memories", {})

        if not isinstance(memories, dict):
            raise ValueError("Invalid memory list")

        reply = _format_memories_naturally(memories)

        # RIA_M86_OPTIONAL_MEMORY_NARRATION
        import os
        if (
            memories
            and os.getenv("RIA_DYNAMIC_MEMORY_NARRATION") == "1"
        ):
            try:
                from ria1.scripts.module44_memory_narration import (
                    narrate_memories,
                )
                generated = narrate_memories(
                    memories,
                    user_message=user_message,
                )
                if generated:
                    reply = generated
            except Exception as exc:
                print(
                    "RIA memory narration fallback:",
                    type(exc).__name__,
                    flush=True,
                )

    elif action == "reminder_created":
        reminder = result.get("reminder")

        if not isinstance(reminder, dict):
            raise ValueError("Missing confirmed reminder")

        reply = "Done! Your reminder is scheduled."

    elif action == "conversation":
        reply = result.get("reply")

        if not isinstance(reply, str):
            raise ValueError("Invalid conversation reply")

    else:
        raise ValueError("Unknown successful action")

    return {
        **result,
        "reply": reply,
    }


def uncertain_execution_response():
    """Do not retry an action whose outcome may be unknown."""
    return {
        "action": "execution_uncertain",
        "success": False,
        "reply": (
            "I couldn't confirm whether that action finished. "
            "Please check your reminders or saved memories "
            "before trying again."
        ),
    }
