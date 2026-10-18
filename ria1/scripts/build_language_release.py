
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

APPROVED = ROOT / "ria1/data/language_foundation/approved"
AUDIT = ROOT / "ria1/data/audit/language_foundation_full_audit.json"
BENCHMARK = (
    ROOT / "ria1/data/evaluation/"
    "tanglish_comprehension_v1.jsonl"
)

RELEASE = ROOT / "ria1/data/releases/language_foundation_v1"

CHAT = APPROVED / "language_all_chat.jsonl"
MEANINGS = APPROVED / "language_all_meanings.jsonl"
SOURCE_REPORT = APPROVED / "language_all_report.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(row, ensure_ascii=False) + "\n"
            )


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    # Do not silently replace a previously frozen release.
    if RELEASE.exists():
        raise FileExistsError(
            f"Release already exists: {RELEASE}\n"
            "Choose a new version for a new release."
        )

    audit = read_json(AUDIT)
    source_report = read_json(SOURCE_REPORT)

    chats = read_jsonl(CHAT)
    meanings = read_jsonl(MEANINGS)
    benchmark = read_jsonl(BENCHMARK)

    if audit["errors"]:
        raise ValueError("Structural audit errors remain")

    for key in (
        "script_warnings",
        "internal_duplicate_warnings",
        "benchmark_overlap_warnings",
        "pilot_overlap_warnings",
    ):
        if audit[key]:
            raise ValueError(
                f"Audit warnings remain: {key}"
            )

    if len(chats) != 124 or len(meanings) != 124:
        raise ValueError("Expected 124 exported examples")

    if source_report["approved"] != 125:
        raise ValueError("Expected 125 approved records")

    if len(benchmark) != 30:
        raise ValueError("Expected 30 held-out benchmark cases")

    # Verify the audited files have not changed.
    if hash_file(CHAT) != audit["chat_sha256"]:
        raise ValueError("Chat data changed after audit")

    if hash_file(MEANINGS) != audit["meaning_sha256"]:
        raise ValueError("Meaning data changed after audit")

    if hash_file(BENCHMARK) != audit["benchmark_sha256"]:
        raise ValueError("Benchmark changed after audit")

    chat_map = {r["id"]: r for r in chats}
    meaning_map = {r["id"]: r for r in meanings}

    if (
        len(chat_map) != 124
        or len(meaning_map) != 124
        or set(chat_map) != set(meaning_map)
    ):
        raise ValueError("Mismatched or duplicate IDs")

    conversation_rows = []
    comprehension_rows = []
    categories = Counter()

    for record in chats:
        rid = record["id"]
        meaning = meaning_map[rid]
        messages = record["messages"]

        if record.get("review_status") != "human_approved":
            raise ValueError(f"Not human approved: {rid}")

        roles = [message["role"] for message in messages]

        if roles not in (
            ["user", "assistant"],
            ["user", "assistant", "user", "assistant"],
        ):
            raise ValueError(f"Invalid conversation: {rid}")

        categories[record["category"]] += 1

        # Conversation training candidate.
        # Keep previous context intact.
        conversation_rows.append({
            "id": rid,
            "category": record["category"],
            "messages": messages,
        })

        # Separate comprehension training candidate.
        # The output target is an English meaning, not a
        # conversational response.
        previous_context = ""

        if len(messages) == 4:
            previous_context = (
                "Previous user: "
                + messages[0]["content"]
                + "\nPrevious Ria: "
                + messages[1]["content"]
                + "\n"
            )

        comprehension_input = (
            previous_context
            + "Current user: "
            + messages[-2]["content"]
        )

        comprehension_rows.append({
            "id": rid,
            "category": record["category"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Understand conversational Tanglish. "
                        "Explain exactly what the CURRENT USER "
                        "means in one concise English sentence. "
                        "Use prior context when provided. "
                        "Preserve pronouns, tense and negation. "
                        "Do not answer the user's request."
                    ),
                },
                {
                    "role": "user",
                    "content": comprehension_input,
                },
                {
                    "role": "assistant",
                    "content": meaning["english_meaning"],
                },
            ],
        })

    RELEASE.mkdir(parents=True, exist_ok=False)

    conversation_path = RELEASE / "conversation_candidates.jsonl"
    comprehension_path = RELEASE / "comprehension_candidates.jsonl"
    meaning_path = RELEASE / "meaning_reference.jsonl"

    write_jsonl(conversation_path, conversation_rows)
    write_jsonl(comprehension_path, comprehension_rows)
    write_jsonl(meaning_path, meanings)

    files = [
        conversation_path,
        comprehension_path,
        meaning_path,
    ]

    manifest = {
        "release": "language_foundation_v1",
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "pilot_release_candidate",
        "human_approved_source_count": 125,
        "released_record_count": 124,
        "multi_turn_count": sum(
            len(r["messages"]) == 4
            for r in conversation_rows
        ),
        "categories": dict(categories),
        "held_out_benchmark": str(BENCHMARK),
        "held_out_benchmark_sha256": hash_file(BENCHMARK),
        "source_chat_sha256": hash_file(CHAT),
        "source_meanings_sha256": hash_file(MEANINGS),
        "source_audit_sha256": hash_file(AUDIT),
        "files": {
            p.name: {
                "records": len(read_jsonl(p)),
                "sha256": hash_file(p),
            }
            for p in files
        },
        "limitations": [
            "Language quality is human-reviewed but not independently verified.",
            "Similarity screening cannot rule out all semantic leakage.",
            "No train/validation split has been created.",
            "No model-specific chat template has been applied.",
            "Past assistant turns may require loss masking during SFT.",
            "Training and production readiness have not been established.",
        ],
    }

    manifest_path = RELEASE / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print("\nRIA-1 LANGUAGE FOUNDATION RELEASE V1")
    print("=" * 55)
    print("Approved source records: 125")
    print("Released records:", len(conversation_rows))
    print("Multi-turn records:", manifest["multi_turn_count"])
    print("Conversation candidates:", len(conversation_rows))
    print("Comprehension candidates:", len(comprehension_rows))
    print("Benchmark cases excluded from release:", len(benchmark))
    print("Release:", RELEASE)
    print("Manifest:", manifest_path)
    print("Status: Pilot release candidate")
    print("Training started: No")


if __name__ == "__main__":
    main()

