"""Conservative, context-sensitive reply cleanup for RIA."""

import re


EXCITEMENT_CUES = (
    "exciting", "amazing news", "guess what",
    "good news", "great news", "i got selected",
    "i got the job", "i won", "surprise",
)


def clean_reply(text: str, user_message: str = "") -> str:
    reply = text.strip()
    user = user_message.lower()

    # Allow genuine excitement when the user's message invites it.
    excited = any(cue in user for cue in EXCITEMENT_CUES)

    if not excited:
        reply = re.sub(
            r"^(?:(?:o{2,}h+|a+h{2,}|okay+y+)[!,. \t]*)+",
            "",
            reply,
            flags=re.IGNORECASE,
        ).strip()

    # Restore capitalization if an opening filler was removed.
    if reply and reply[0].islower():
        reply = reply[0].upper() + reply[1:]

    return reply
