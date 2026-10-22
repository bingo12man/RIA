import json

ALLOWED_KEYS = {"instrument"}
MAX_VALUE_LENGTH = 200


def build_memory_context(memories):
    """
    Prepare permitted memory data for the LLM.

    Authorization and size limits are deterministic.
    Conversation interpretation belongs to the LLM.
    """
    selected = {}

    for key, value in memories.items():
        if key not in ALLOWED_KEYS:
            continue

        if not isinstance(value, str):
            continue

        selected[key] = value[:MAX_VALUE_LENGTH]

    return json.dumps(
        selected,
        ensure_ascii=False,
    )
