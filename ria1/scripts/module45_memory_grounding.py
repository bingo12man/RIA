"""RIA M8.7: validate LLM-selected memory references."""

def validate_memory_selection(selection, memories):
    if not isinstance(memories, dict):
        raise ValueError("Invalid memory collection")

    if not isinstance(selection, dict):
        raise ValueError("Invalid selection")

    if set(selection) != {"memory_ids"}:
        raise ValueError("Unexpected selection fields")

    ids = selection["memory_ids"]

    if not isinstance(ids, list):
        raise ValueError("Memory IDs must be a list")

    if len(ids) > len(memories):
        raise ValueError("Selection exceeds available memories")

    if any(not isinstance(i, str) for i in ids):
        raise ValueError("Invalid memory ID")

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate memory IDs")

    if any(i not in memories for i in ids):
        raise ValueError("Unknown memory ID")

    return {
        memory_id: memories[memory_id]
        for memory_id in ids
    }
