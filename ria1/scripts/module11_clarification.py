"""Clarification rules for RIA-1."""

import re

UNCLEAR_SPEECH_REPLY = (
    "Sorry, I didn't catch that. "
    "Could you say it again, please?"
)

AMBIGUOUS_QUERY_REPLY = (
    "I'm not quite sure what you mean. "
    "Could you explain a little more?"
)

# These are fragments, not complete instructions.
UNCLEAR_FRAGMENTS = {
    "oh", "uh", "um", "ah", "hmm", "huh",
    "ad", "erm", "mmm",
}


def speech_needs_clarification(
    transcript: str,
    *,
    rejected: bool = False,
    rejection_reason: str | None = None,
) -> bool:
    if rejected:
        # Don't respond to recordings rejected as silence/no speech.
        return rejection_reason not in {
            "no_speech_activity",
            "silence",
        }

    text = transcript.strip()
    if not text:
        return False

    normalized = re.sub(
        r"[^\w\s]", "", text.lower()
    ).strip()

    return normalized in UNCLEAR_FRAGMENTS
