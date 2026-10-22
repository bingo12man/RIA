import re

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40,
    "forty five": 45, "sixty": 60,
    "an": 1, "a": 1,
}

NUMBER = r"(\d+|" + "|".join(
    re.escape(w) for w in sorted(NUMBER_WORDS, key=len, reverse=True)
) + r")"


def parse_minutes(value):
    if value.isdigit():
        return int(value)
    return NUMBER_WORDS.get(value)



# RIA_P048_REMINDER_PATCH

def parse_voice_command(text: str) -> dict:
    """Interpret explicit reminder commands without an LLM."""
    original = text.strip()
    cleaned = original.lower().strip(" .!?")

    # Normalize common wake-word transcription variations.
    cleaned = re.sub(
        r"^(?:(?:hey|hi|oh)\s+)?(?:ria|riya|rhea|ariya)[,\s]+",
        "",
        cleaned,
    )

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^please\s+", "", cleaned)

    # RIA_P1641_NATURAL_REMINDER
    # RIA_P1644_COMMAND_FIRST
    # Find a recognized reminder command after an optional short address.
    # Do not modify the task or time after the command begins.
    reminder_starts = (
        "can you remind me to",
        "could you remind me to",
        "can you set me a reminder to",
        "could you set me a reminder to",
        "can you send me a reminder to",
        "could you send me a reminder to",
        "remind me to",
        "set a reminder to",
        "set a reminder for me to",
        "give me a reminder to",
        "send me a reminder to",
        "create a reminder to",
    )

    for phrase in sorted(reminder_starts, key=len, reverse=True):
        position = cleaned.find(phrase)

        if position == -1:
            continue

        before = cleaned[:position].strip(" ,")

        # Accept a short wake word or greeting, not arbitrary instructions.
        if position == 0 or (
            len(before.split()) <= 3
            and re.fullmatch(r"[a-z]+(?:[ ,]+[a-z]+){0,2}", before)
        ):
            cleaned = cleaned[position:]
            break

    # Supported natural reminder phrases.
    create_prefix = (
        r"(?:remind me to|"
        r"set a reminder to|"
        r"set a reminder for me to|"
        r"give me a reminder to|"
        r"send me a reminder to|"
        r"can you send me a reminder to|"
        r"could you send me a reminder to|"
        r"create a reminder to|"
        r"can you remind me to|"
        r"could you remind me to|"
        r"can you set me a reminder to|"
        r"could you set me a reminder to|"
        r"can you set a reminder to)"
    )

    time_pattern = (
        r"(?:in|after)\s+(?:(?:the\s+)?next\s+)?"
        + NUMBER
        + r"\s+(minutes?|hours?)"
    )

    create_pattern = (
        r"^"
        + create_prefix
        + r"\s+(.+?)\s+"
        + time_pattern
        + r"$"
    )

    match = re.fullmatch(create_pattern, cleaned)

    if match:
        task, value, unit = match.groups()
        minutes = parse_minutes(value)

        if minutes is None:
            return {
                "action": "clarify",
                "reply": "How many minutes from now?"
            }

        if unit.startswith("hour"):
            minutes *= 60

        if not task.strip() or not 1 <= minutes <= 525600:
            return {
                "action": "clarify",
                "reply": "What should I remind you to do, and when?"
            }

        return {
            "action": "create",
            "title": task.strip(),
            "minutes": minutes,
        }

    # Example: Give me a reminder to drink water next minute.
    next_minute_pattern = (
        r"^"
        + create_prefix
        + r"\s+(.+?)\s+(?:in\s+the\s+)?next\s+minute$"
    )

    match = re.fullmatch(next_minute_pattern, cleaned)

    if match:
        return {
            "action": "create",
            "title": match.group(1).strip(),
            "minutes": 1,
        }

    # Snooze the currently due reminder.
    snooze_pattern = (
        r"^snooze\s+(?:that|it|my reminder|the reminder)"
        r"(?:\s+for\s+"
        + NUMBER
        + r"\s+minutes?)?$"
    )

    match = re.fullmatch(snooze_pattern, cleaned)

    if match:
        value = match.group(1)
        minutes = parse_minutes(value) if value else 5

        if minutes is None or not 1 <= minutes <= 1440:
            return {
                "action": "clarify",
                "reply": "How many minutes should I snooze it?"
            }

        return {
            "action": "snooze",
            "minutes": minutes,
        }

    if cleaned in {
        "done",
        "mark it done",
        "mark my reminder done",
        "mark my reminder as done",
        "mark that as done",
        "i did it",
    }:
        return {"action": "done"}

    if cleaned in {
        "skip",
        "skip that",
        "skip my reminder",
        "skip that reminder",
    }:
        return {"action": "skip"}

    # Never send an incomplete reminder request to the LLM.
    if re.search(
        r"\b(?:remind me|reminder|snooze)\b",
        cleaned,
    ):
        return {
            "action": "clarify",
            "reply": (
                "What should I remind you to do, "
                "and in how many minutes?"
            ),
        }

    return {
        "action": "conversation",
        "text": original,
    }

if __name__ == "__main__":
    examples = [
        "Ria, remind me to practice guitar in 10 minutes.",
        "Ria, please remind me to drink water in five minutes.",
        "Ria, snooze that for five minutes.",
        "Ria, mark my reminder as done.",
        "Ria, skip that reminder.",
        "Ria, remind me to take a break.",
        "Ria, how are you?",
    ]

    for sentence in examples:
        print(sentence)
        print(" =>", parse_voice_command(sentence))
        print()
