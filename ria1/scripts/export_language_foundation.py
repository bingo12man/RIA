
import json
import hashlib
import difflib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "ria1/data/language_foundation"
EVAL_DIR = ROOT / "ria1/data/evaluation"

SOURCE = DATA_DIR / "pronouns_verbs_001.jsonl"
REVIEWS = DATA_DIR / "pronouns_verbs_001_reviews.json"
BENCHMARK = EVAL_DIR / "tanglish_comprehension_v1.jsonl"

OUT = DATA_DIR / "approved"
CHAT_OUT = OUT / "pronouns_verbs_001_chat.jsonl"
MEANING_OUT = OUT / "pronouns_verbs_001_meanings.jsonl"
REPORT = OUT / "pronouns_verbs_001_audit.json"


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def normalize(text):
    return " ".join(text.casefold().split())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(row, ensure_ascii=False) + "\n"
            )


def main():
    source = read_jsonl(SOURCE)
    benchmark = read_jsonl(BENCHMARK)

    reviews = json.loads(
        REVIEWS.read_text(encoding="utf-8")
    )["reviews_by_id"]

    ids = [row["id"] for row in source]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source IDs")

    if set(ids) != set(reviews):
        raise ValueError(
            "Some source records are not reviewed, "
            "or review IDs do not match"
        )

    chat_rows = []
    meaning_rows = []
    warnings = []
    counts = Counter()

    for row in source:
        record_id = row["id"]
        review = reviews[record_id]
        status = review["status"]
        counts[status] += 1

        if status != "approved":
            continue

        user = row["user_message"].strip()
        meaning = review["english_meaning"].strip()
        tamil = review["tamil_equivalent"].strip()
        response = review["ria_response"].strip()

        if not all([user, meaning, tamil, response]):
            raise ValueError(
                f"Incomplete approved record: {record_id}"
            )

        for case in benchmark:
            similarity = difflib.SequenceMatcher(
                None,
                normalize(user),
                normalize(case["user_message"]),
            ).ratio()

            if similarity >= 0.78:
                warnings.append({
                    "training_id": record_id,
                    "benchmark_id": case["id"],
                    "similarity": round(similarity, 3),
                    "training_prompt": user,
                    "benchmark_prompt": case["user_message"],
                })

        meaning_rows.append({
            "id": record_id,
            "tanglish": user,
            "english_meaning": meaning,
            "tamil_equivalent": tamil,
            "review_status": "human_approved",
        })

        chat_rows.append({
            "id": record_id,
            "language": "tanglish",
            "user_message": user,
            "assistant_response": response,
            "review_status": "human_approved",
        })

    # Block release of candidates matching the held-out test.
    flagged_ids = {
        item["training_id"] for item in warnings
    }

    safe_meanings = [
        r for r in meaning_rows
        if r["id"] not in flagged_ids
    ]
    safe_chat = [
        r for r in chat_rows
        if r["id"] not in flagged_ids
    ]

    OUT.mkdir(parents=True, exist_ok=True)

    save_jsonl(CHAT_OUT, safe_chat)
    save_jsonl(MEANING_OUT, safe_meanings)

    report = {
        "source_records": len(source),
        "reviewed": len(reviews),
        "approved": counts["approved"],
        "rejected": counts["rejected"],
        "excluded_for_similarity_review": sorted(
            flagged_ids
        ),
        "exported": len(safe_chat),
        "benchmark_similarity_warnings": warnings,
        "source_sha256": sha256(SOURCE),
        "reviews_sha256": sha256(REVIEWS),
        "benchmark_sha256": sha256(BENCHMARK),
        "chat_sha256": sha256(CHAT_OUT),
        "meanings_sha256": sha256(MEANING_OUT),
        "status": (
            "Exported for further review. "
            "Not automatically approved for training."
        ),
    }

    REPORT.write_text(
        json.dumps(
            report, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )

    print("\nRIA-1 LANGUAGE FOUNDATION EXPORT")
    print("=" * 50)
    print("Source records:", len(source))
    print("Reviewed:", len(reviews))
    print("Approved:", counts["approved"])
    print("Rejected:", counts["rejected"])
    print("Similarity warnings:", len(warnings))
    print("Excluded pending review:", len(flagged_ids))
    print("Exported:", len(safe_chat))
    print("Chat export:", CHAT_OUT)
    print("Meaning export:", MEANING_OUT)
    print("Audit report:", REPORT)


if __name__ == "__main__":
    main()

