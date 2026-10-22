"""RIA P1.6.3 — Conservative tool argument grounding.

Only explicitly supported phrases are authorized.
Unrecognized phrasing must not result in a persistent write.
"""

import re

NUMBERS = {
    "one": 1, "two": 2, "three": 3,
    "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30,
    "sixty": 60,
}

def normalize(text):
    if not isinstance(text, str):
        return ""
    return " ".join(
        text.casefold().strip().rstrip(".!? ").split()
    )

def clean_message(message):
    text = normalize(message)
    return re.sub(
        r"^(?:(?:hey|hi|oh)\s+)?(?:ria|riya|rhea)[,\s]+",
        "",
        text,
    ).strip()

def grounded(message, name, args):
    """Compare a proposed tool to explicitly expressed intent.

    Fail closed. This is a narrow grounding check, not a
    comprehensive semantic authorization engine.
    """
    if not isinstance(args, dict):
        return False

    text = clean_message(message)

    if name == "memory_list":
        return args == {} and text in {
            "what do you remember about me",
            "do you remember about me",
            "do you remember anything about me",
            "what do you know about me",
            "show my memories",
        }

    if name == "memory_save":
        match = re.fullmatch(
            r"(?:please )?remember that (.+)", text
        )
        return (
            match is not None
            and set(args) == {"fact"}
            and normalize(args["fact"]) == match.group(1)
        )

    if name == "memory_forget":
        match = re.fullmatch(
            r"(?:please )?(?:forget|delete|remove) "
            r"(?:that )?(.+)",
            text,
        )
        if not match or set(args) != {"exact_fact"}:
            return False

        target = match.group(1)

        if target in {
            "everything", "all", "all memories",
            "my memories", "everything about me",
        }:
            return False

        return normalize(args["exact_fact"]) == target

    if name == "memory_update":
        if set(args) != {"old_fact", "new_fact"}:
            return False

        match = re.fullmatch(
            r"(?:please )?(?:change|update|correct) "
            r"(?:my |my saved )?preference from "
            r"(.+?) to (.+)",
            text,
        )

        if not match:
            return False

        old_value, new_value = match.groups()

        return (
            normalize(args["old_fact"]) ==
            "i prefer " + old_value
            and
            normalize(args["new_fact"]) ==
            "i prefer " + new_value
            and old_value != new_value
        )

    if name == "reminder_create":
        # RIA_P1811_LLM_FIRST_REMINDER
        from ria1.scripts.module15_reminder_safety import safe_reminder
        return safe_reminder(message, args)

    return False
