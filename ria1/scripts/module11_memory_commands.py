"""User-controlled conversational memories for RIA."""

import hashlib
import re

from ria1.scripts.module5_memory import (
    save_memory,
    get_memories,
    delete_memory,
    replace_memory,
)

PREFIX = re.compile(
    r"^\s*(?:(?:hey|hi|oh|okay|ok)\s+)?(?:ria|riya|rhea|horia)\b[\s,!?.:-]*",
    re.IGNORECASE,
)

REMEMBER = re.compile(
    r"^(?:please\s+)?remember\s+that\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)

LIST_MEMORY = re.compile(
    r"^(?:what\s+do\s+you\s+remember\s+about\s+me|"
    r"show\s+my\s+memories|"
    r"what\s+have\s+you\s+saved\s+about\s+me)"
    r"\s*[?.!]*$",
    re.IGNORECASE,
)


def memory_key(fact: str) -> str:
    normalized = " ".join(fact.casefold().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"fact_{digest}"



def format_memory_for_speech(memories: dict) -> str:
    if not memories:
        return "Hmm, I don't have anything saved about you yet!"

    facts = []

    for key, value in memories.items():
        value = value.strip().rstrip(".!?")
        lower = value.lower()

        if key == "instrument" and lower == "guitar":
            facts.append("you play guitar")
        elif lower.startswith("i "):
            facts.append("you " + value[2:])
        elif lower.startswith("my "):
            facts.append("your " + value[3:])
        else:
            facts.append(value)

    if len(facts) == 1:
        summary = facts[0]
    elif len(facts) == 2:
        summary = " and ".join(facts)
    else:
        summary = ", ".join(facts[:-1]) + ", and " + facts[-1]

    return (
        "Here's what I remember about you. "
        + summary[0].upper()
        + summary[1:]
        + ". That's what I've got so far!"
    )



# RIA_P053_NATURAL_MEMORY_COMMANDS

def _fact(value):
    return value.strip().rstrip(".!? ").strip()


def _normalize(value):
    return " ".join(_fact(value).casefold().split())


def _response(action, reply):
    return {"handled": True, "action": action, "reply": reply}


def _preference(value):
    match = re.fullmatch(
        r"(?:i prefer|my preference is)\s+(.+)",
        _normalize(value),
    )
    return match.group(1) if match else None


def _preference_matches(memories):
    return [
        (key, value)
        for key, value in memories.items()
        if _preference(value) is not None
    ]


def handle_memory_command(message: str, user_id: str):
    text = PREFIX.sub("", message.strip(), count=1).strip()
    text = _fact(text)
    normalized = _normalize(text)

    # Recall existing memories.
    if LIST_MEMORY.fullmatch(text):
        return _response(
            "memory_listed",
            format_memory_for_speech(get_memories(user_id)),
        )

    # Explicit forgetting: never delete on a fuzzy match.
    forget = re.fullmatch(
        r"(?:please\s+)?(?:forget|delete|remove)\s+"
        r"(?:that\s+)?(.+)",
        text,
        re.IGNORECASE,
    )

    if forget:
        target = _normalize(forget.group(1))

        if target in {"everything", "all", "all memories",
                      "my memories", "everything about me"}:
            return _response(
                "memory_invalid",
                "I won't erase everything from that command. "
                "Please specify the memory to forget.",
            )

        memories = get_memories(user_id)
        matches = [
            key for key, value in memories.items()
            if _normalize(value) == target
        ]

        if len(matches) != 1:
            return _response(
                "memory_invalid",
                "I couldn't identify exactly one matching memory. "
                "Ask what I remember, then tell me the exact fact to forget.",
            )

        if delete_memory(user_id, matches[0]):
            return _response(
                "memory_deleted",
                "Okay, I've removed that saved memory.",
            )

        return _response(
            "memory_error",
            "That memory couldn't be deleted.",
        )

    # Explicit correction: "change my preference from tea to coffee".
    change = re.fullmatch(
        r"(?:please\s+)?(?:change|update|correct)\s+"
        r"my preference from (.+?) to (.+)",
        text,
        re.IGNORECASE,
    )

    if change:
        old_value = _normalize(change.group(1))
        new_value = _fact(change.group(2))

        if not new_value or len(new_value) > 480:
            return _response(
                "memory_invalid",
                "Please give me a shorter, clearer preference.",
            )

        memories = get_memories(user_id)
        matches = [
            (key, value)
            for key, value in _preference_matches(memories)
            if _preference(value) == old_value
        ]

        if len(matches) != 1:
            return _response(
                "memory_invalid",
                "I couldn't find exactly one matching old preference.",
            )

        new_fact = "I prefer " + new_value

        try:
            replaced = replace_memory(
                user_id,
                matches[0][0],
                memory_key(new_fact),
                new_fact,
            )
        except ValueError as exc:
            return _response("memory_error", str(exc))

        return _response(
            "memory_updated" if replaced else "memory_error",
            "Got it, I've updated your preference."
            if replaced else "I couldn't update that memory.",
        )

    # Explicit memory saving.
    remember = REMEMBER.fullmatch(text)

    if remember:
        fact = _fact(remember.group(1))
        if not fact or len(fact) > 500:
            return _response(
                "memory_invalid",
                "Could you say that a little more clearly?",
            )
    else:
        # Natural preference changes require an explicit present-time cue.
        natural = re.fullmatch(
            r"(?:(?:actually|now|instead|i changed my mind)\s*,?\s*)?"
            r"i prefer (.+?) now",
            text,
            re.IGNORECASE,
        )

        if not natural:
            natural = re.fullmatch(
                r"(?:actually|instead|i changed my mind)\s*,?\s*"
                r"i prefer (.+)",
                text,
                re.IGNORECASE,
            )

        if not natural:
            # Prevent unsupported memory instructions reaching the LLM.
            if re.match(
                r"^(?:please\s+)?(?:remember|forget|"
                r"delete my memory|change my preference|"
                r"update my preference)\b",
                normalized,
            ):
                return _response(
                    "memory_invalid",
                    "Please tell me exactly what to remember or change.",
                )
            return {"handled": False}

        fact = "I prefer " + _fact(natural.group(1))

        if len(fact) > 500:
            return _response(
                "memory_invalid",
                "That preference is too long to save.",
            )

    memories = get_memories(user_id)
    new_preference = _preference(fact)

    # Replace a unique preference, but never guess between several.
    if new_preference is not None:
        existing = _preference_matches(memories)

        if len(existing) > 1:
            return _response(
                "memory_invalid",
                "I found several saved preferences. "
                "Please tell me which old preference to change.",
            )

        if len(existing) == 1:
            old_key, old_fact = existing[0]

            if _normalize(old_fact) == _normalize(fact):
                return _response(
                    "memory_saved",
                    "I already have that preference saved.",
                )

            try:
                replaced = replace_memory(
                    user_id,
                    old_key,
                    memory_key(fact),
                    fact,
                )
            except ValueError as exc:
                return _response("memory_error", str(exc))

            return _response(
                "memory_updated" if replaced else "memory_error",
                "Got it, I've updated your preference."
                if replaced else "I couldn't update that memory.",
            )

    try:
        save_memory(user_id, memory_key(fact), fact)
    except ValueError as exc:
        return _response(
            "memory_error",
            "I couldn't save that memory: " + str(exc),
        )

    return _response(
        "memory_saved",
        "Got it! I'll remember that.",
    )
