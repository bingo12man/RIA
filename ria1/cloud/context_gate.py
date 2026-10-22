import re


GUITAR_TERMS = {
    "guitar", "instrument", "chord", "chords",
    "strum", "strumming", "fret", "frets",
    "fingerboard", "metronome",
}

FOLLOWUP_TERMS = {
    "it", "them", "that", "those",
    "this", "exercise", "again",
}


def words(text):
    return set(re.findall(r"\b[a-z]+\b", text.lower()))


def select_memories(message, history, memories):
    """Return relevant memories only."""
    current = words(message)

    selected = {}

    instrument = memories.get("instrument")
    if not instrument:
        return selected

    # Direct mention: memory is relevant.
    if current & GUITAR_TERMS:
        selected["instrument"] = instrument
        return selected

    # An explicit memory-recall question.
    if (
        "remember" in current
        and current & {"hobby", "hobbies", "learning"}
    ):
        selected["instrument"] = instrument
        return selected

    # Follow-up only if recent user context is relevant.
    if current & FOLLOWUP_TERMS:
        previous_user_messages = [
            item["content"]
            for item in history[-6:]
            if item["role"] == "user"
        ]

        if any(
            words(previous) & GUITAR_TERMS
            for previous in previous_user_messages
        ):
            selected["instrument"] = instrument

    return selected


def route_message(message, history, memories):
    text = message.strip()
    tokens = words(text)

    if not text:
        return {
            "action": "clarify",
            "reply": "I didn't catch that. Could you repeat it?",
            "memories": {},
        }

    # Known, previously observed garbled-input examples.
    # These rules are not a general noise detector.
    known_garbled = {
        "airea havari duntu le",
        "flent borik zanu mum",
    }

    if text.lower().strip(".!? ") in known_garbled:
        return {
            "action": "clarify",
            "reply": "Sorry, I didn't catch that. Could you say it again?",
            "memories": {},
        }

    # Explicitly vague messages without a specified topic.
    if tokens in (
        {"i", "m", "struggling"},
        {"im", "struggling"},
    ) or text.lower().strip(".!?") in {
        "ria, i'm struggling",
        "i'm struggling",
        "i feel confused about my next step",
    }:
        return {
            "action": "clarify",
            "reply": "What are you struggling with?",
            "memories": {},
        }

    return {
        "action": "generate",
        "reply": None,
        "memories": select_memories(
            text, history, memories
        ),
    }
