"""RIA M8.11: typed, inert memory records."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    value: str
    source: str
    kind: str = "unclassified"


def validate_memory_record(record):
    if not isinstance(record, MemoryRecord):
        raise ValueError("Invalid memory record")

    if not record.memory_id or not isinstance(record.memory_id, str):
        raise ValueError("Invalid memory ID")

    if not isinstance(record.value, str) or not record.value.strip():
        raise ValueError("Invalid memory value")

    if len(record.value) > 500:
        raise ValueError("Memory value too long")

    if record.source not in {
        "user_approved",
        "legacy_unverified",
    }:
        raise ValueError("Invalid memory source")

    if record.kind not in {
        "unclassified",
        "preference",
        "personal_fact",
        "quoted_content",
    }:
        raise ValueError("Invalid memory kind")

    return record



def require_approved_memory(record):
    """Require an approved source after structural validation."""
    validate_memory_record(record)

    if record.source != "user_approved":
        raise ValueError("Memory approval is not verified")

    return record


def records_from_memories(memories):
    if not isinstance(memories, dict):
        raise ValueError("Invalid memory collection")

    return [
        validate_memory_record(
            MemoryRecord(
                memory_id=key,
                value=value,
                source="legacy_unverified",
            )
        )
        for key, value in memories.items()
    ]
