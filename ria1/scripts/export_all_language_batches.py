
import difflib
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "ria1/data/language_foundation"
OUT = DATA / "approved"

BENCHMARK = (
    ROOT / "ria1/data/evaluation/"
    "tanglish_comprehension_v1.jsonl"
)

BATCHES = [
    "pronouns_verbs_001",
    "everyday_vocabulary_001",
    "negation_corrections_001",
    "emotion_intent_001",
    "context_switching_001",
]

FIELDS = (
    "english_meaning",
    "tamil_equivalent",
    "ria_response",
)


def read_jsonl(path):
    rows = []

    with path.open("r", encoding="utf-8") as file:
        for number, line in enumerate(file, 1):
            if line.strip():
                row = json.loads(line)

                if not isinstance(row, dict):
                    raise ValueError(
                        f"Invalid JSON object: {path}:{number}"
                    )

                rows.append(row)

    return rows


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def normalize(text):
    return " ".join(text.casefold().split())


def sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def atomic_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)

            for row in rows:
                file.write(
                    json.dumps(row, ensure_ascii=False)
                    + "\n"
                )

        os.replace(temporary, path)

    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)

            json.dump(
                value,
                file,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(temporary, path)

    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def build_chat_messages(source, response):
    messages = []

    previous_user = source.get("previous_user")
    previous_ria = source.get("previous_ria")

    has_context = (
        previous_user is not None
        or previous_ria is not None
    )

    if has_context:
        if (
            not isinstance(previous_user, str)
            or not previous_user.strip()
            or not isinstance(previous_ria, str)
            or not previous_ria.strip()
        ):
            raise ValueError(
                f"Incomplete context: {source['id']}"
            )

        messages.extend([
            {
                "role": "user",
                "content": previous_user.strip(),
            },
            {
                "role": "assistant",
                "content": previous_ria.strip(),
            },
        ])

    messages.extend([
        {
            "role": "user",
            "content": source["user_message"].strip(),
        },
        {
            "role": "assistant",
            "content": response.strip(),
        },
    ])

    return messages


def find_benchmark_overlap(messages, benchmark):
    matches = []

    user_turns = [
        message["content"]
        for message in messages
        if message["role"] == "user"
    ]

    for user_text in user_turns:
        for case in benchmark:
            score = difflib.SequenceMatcher(
                None,
                normalize(user_text),
                normalize(case["user_message"]),
            ).ratio()

            if score >= 0.78:
                matches.append({
                    "benchmark_id": case["id"],
                    "similarity": round(score, 3),
                    "training_prompt": user_text,
                    "benchmark_prompt": case["user_message"],
                })

    return matches


def main():
    benchmark = read_jsonl(BENCHMARK)

    chats = []
    meanings = []

    approved = 0
    rejected = 0

    unreviewed = []
    blocked = []

    ids = set()
    prompts = set()

    source_hashes = {}
    counts = Counter()

    for batch in BATCHES:
        source_path = DATA / f"{batch}.jsonl"
        reviews_path = DATA / f"{batch}_reviews.json"

        source_rows = read_jsonl(source_path)
        reviews = read_json(
            reviews_path
        )["reviews_by_id"]

        source_hashes[batch] = {
            "source": sha256(source_path),
            "reviews": sha256(reviews_path),
        }

        source_ids = [
            str(row["id"])
            for row in source_rows
        ]

        if len(source_ids) != len(set(source_ids)):
            raise ValueError(
                f"Duplicate source IDs in {batch}"
            )

        if not set(reviews).issubset(set(source_ids)):
            raise ValueError(
                f"Unknown review IDs in {batch}"
            )

        for source in source_rows:
            rid = str(source["id"])

            if rid in ids:
                raise ValueError(
                    f"Duplicate global record ID: {rid}"
                )

            ids.add(rid)

            review = reviews.get(rid)

            if review is None:
                unreviewed.append(rid)
                continue

            status = review.get("status")

            if status == "rejected":
                rejected += 1
                continue

            if status != "approved":
                raise ValueError(
                    f"Unknown review status for {rid}: {status}"
                )

            approved += 1

            for field in FIELDS:
                value = review.get(field)

                if (
                    not isinstance(value, str)
                    or not value.strip()
                ):
                    raise ValueError(
                        f"{rid}: missing {field}"
                    )

            user = source["user_message"].strip()
            response = review["ria_response"].strip()

            prompt_key = normalize(user)

            if prompt_key in prompts:
                raise ValueError(
                    f"Duplicate training prompt: {rid}"
                )

            prompts.add(prompt_key)

            messages = build_chat_messages(
                source,
                response,
            )

            matches = find_benchmark_overlap(
                messages,
                benchmark,
            )

            if matches:
                blocked.append({
                    "id": rid,
                    "training_prompt": user,
                    "matches": matches,
                })
                continue

            chats.append({
                "id": rid,
                "batch": batch,
                "category": source["category"],
                "language": "tanglish",
                "tone": "neutral",
                "messages": messages,
                "review_status": "human_approved",
            })

            meanings.append({
                "id": rid,
                "batch": batch,
                "category": source["category"],
                "tanglish": user,
                "english_meaning": (
                    review["english_meaning"].strip()
                ),
                "tamil_equivalent": (
                    review["tamil_equivalent"].strip()
                ),
                "review_status": "human_approved",
            })

            counts[batch] += 1

    if unreviewed:
        raise ValueError(
            "Unreviewed records: "
            + ", ".join(unreviewed)
        )

    assert len(chats) == len(meanings)

    chat_path = OUT / "language_all_chat.jsonl"
    meaning_path = OUT / "language_all_meanings.jsonl"
    report_path = OUT / "language_all_report.json"

    atomic_jsonl(chat_path, chats)
    atomic_jsonl(meaning_path, meanings)

    context_count = sum(
        len(item["messages"]) == 4
        for item in chats
    )

    report = {
        "batches": BATCHES,
        "approved": approved,
        "rejected": rejected,
        "unreviewed_ids": unreviewed,
        "exported": len(chats),
        "multi_turn_records": context_count,
        "blocked_for_overlap_review": blocked,
        "exported_by_batch": dict(counts),
        "source_hashes": source_hashes,
        "benchmark_sha256": sha256(BENCHMARK),
        "chat_sha256": sha256(chat_path),
        "meanings_sha256": sha256(meaning_path),
        "training_ready": False,
        "note": (
            "Human-reviewed candidate export. "
            "Multi-turn context preserved. "
            "Requires final semantic and leakage audit."
        ),
    }

    atomic_json(report_path, report)

    print("\nRIA-1 UNIFIED LANGUAGE EXPORT V2")
    print("=" * 50)
    print("Approved:", approved)
    print("Rejected:", rejected)
    print("Unreviewed:", len(unreviewed))
    print("Exported:", len(chats))
    print("Multi-turn records:", context_count)
    print("Blocked for overlap:", len(blocked))

    print("\nExported by batch:")
    for batch in BATCHES:
        print(
            f"  {batch}: {counts[batch]}"
        )

    for item in blocked:
        print("\nBLOCKED:", item["id"])
        for match in item["matches"]:
            print(
                match["benchmark_id"],
                "similarity:",
                match["similarity"],
            )

    print("\nChat file:", chat_path)
    print("Meaning file:", meaning_path)
    print("Report:", report_path)
    print("Training ready: No — final audit pending")


if __name__ == "__main__":
    main()

