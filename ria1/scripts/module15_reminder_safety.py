"""RIA P1.8.11: conservative, independent reminder execution safety."""

import re

NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "forty five": 45,
    "forty-five": 45, "sixty": 60,
}

def normalize(value):
    return re.sub(r"\s+", " ", value.lower().strip())

def safe_reminder(message, args):
    if not isinstance(message, str) or not isinstance(args, dict):
        return False

    if set(args) != {"title", "minutes_from_now"}:
        return False

    title = args.get("title")
    minutes = args.get("minutes_from_now")

    if not isinstance(title, str) or not title.strip():
        return False

    if type(minutes) is not int or not 1 <= minutes <= 1440:
        return False

    if len(title) > 200:
        return False

    text = normalize(message)

    # Fail closed on explicit negation or cancellation.
    if re.search(
        r"\b(don't|dont|do not|never|not|stop|cancel|"
        r"no need|without|shouldn't|wouldn't)\b",
        text,
    ):
        return False

    # Fail closed on hypothetical instructions and examples.
    if re.search(
        r"\b(what if|suppose|hypothetically|imagine|"
        r"for example|as an example|i said|"
        r"if i asked|would you|could you explain)\b",
        text,
    ):
        return False

    # Quotes can indicate that the command is being discussed.
    if any(char in message for char in ['"', "'", "“", "”", "‘", "’"]):
        # Ordinary apostrophes in contractions are already
        # handled above; reject other quoted contexts.
        if not re.search(r"\b(i'm|it's|that's)\b", text):
            return False

    # Require an explicit reminder request.
    if not re.search(r"\b(remind|reminder)\b", text):
        return False

    # The proposed task must appear in the instruction.
    words = re.findall(r"[a-z0-9]+", title.lower())
    if not words:
        return False

    pattern = r"\b" + r"\s+".join(map(re.escape, words)) + r"\b"
    if not re.search(pattern, text):
        return False

    # Require an explicit relative duration in minutes.
    # This is a safety check, not the language-understanding engine.
    duration = re.search(
        r"\b(?:in\s+)?(?:the\s+)?(?:next\s+)?"
        r"(\d{1,4}|[a-z]+(?:[- ][a-z]+)?)"
        r"\s+minutes?\b",
        text,
    )

    if duration is None:
        return False

    raw = duration.group(1)
    spoken_minutes = int(raw) if raw.isdigit() else NUMBERS.get(raw)

    return spoken_minutes == minutes
