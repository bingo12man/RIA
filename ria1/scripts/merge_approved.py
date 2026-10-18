
import difflib
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

BASE = ROOT / "ria1/data/standardized/ria1_v1.jsonl"
BASE_REVIEWS = ROOT / "ria1/data/audit/quality_reviews.json"

PROMPTS = ROOT / "ria1/data/expansion/batch_001.jsonl"
CANDIDATES = (
    ROOT / "ria1/data/expansion/batch_001_candidates.jsonl"
)
BATCH_REVIEWS = (
    ROOT / "ria1/data/expansion/batch_001_reviews.json"
)

OUTPUT = ROOT / "ria1/data/standardized/ria1_v2.jsonl"
REPORT = ROOT / "ria1/data/audit/ria1_v2_report.json"


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text):
    return " ".join(text.casefold().split())


def main():
    base = read_jsonl(BASE)
    prompts = read_jsonl(PROMPTS)
    candidates = read_jsonl(CANDIDATES)

    base_reviews = read_json(BASE_REVIEWS)["reviews_by_id"]
    reviews = read_json(BATCH_REVIEWS)["reviews_by_id"]

    prompt_ids = [str(row["id"]) for row in prompts]
    candidate_ids = [str(row["id"]) for row in candidates]

    if len(prompt_ids) != len(set(prompt_ids)):
        raise ValueError("Duplicate prompt IDs.")

    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Duplicate candidate IDs.")

    if set(prompt_ids) != set(candidate_ids):
        raise ValueError("Prompt and candidate IDs differ.")

    if set(candidate_ids) != set(reviews):
        raise ValueError("Candidate and review IDs differ.")

    prompt_map = {str(row["id"]): row for row in prompts}
    candidate_map = {str(row["id"]): row for row in candidates}

    if set(str(row["id"]) for row in base) != set(base_reviews):
        raise ValueError("Base quality reviews do not match base records.")

    merged = []
    counts = Counter()

    for record in base:
        record_id = str(record["id"])
        review = base_reviews[record_id]

        if review["status"] not in {
            "approved", "edited_approved"
        }:
            continue

        answer = (
            review.get("corrected_response")
            if review["status"] == "edited_approved"
            else record["assistant_response"]
        )

        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"Empty base answer: {record_id}")

        merged.append({
            **record,
            "assistant_response": answer.strip(),
            "source_batch": "legacy",
            "quality_status": review["status"],
        })

    for record_id in prompt_ids:
        prompt = prompt_map[record_id]
        candidate = candidate_map[record_id]
        review = reviews[record_id]

        if candidate["candidate_status"] != "pending_review":
            raise ValueError(
                f"Candidate was not successfully generated: {record_id}"
            )

        for field in ("id", "language", "tone", "user_message"):
            if candidate.get(field) != prompt.get(field):
                raise ValueError(
                    f"Candidate differs from original prompt: "
                    f"{record_id}, field={field}"
                )

        if review["status"] not in {
            "approved", "edited_approved"
        }:
            continue

        answer = (
            review.get("corrected_response")
            if review["status"] == "edited_approved"
            else candidate["candidate_response"]
        )

        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"Empty batch answer: {record_id}")

        merged.append({
            "id": record_id,
            "language": prompt["language"],
            "tone": prompt["tone"],
            "user_message": prompt["user_message"].strip(),
            "assistant_response": answer.strip(),
            "review_status": "approved",
            "source": "original_expansion_prompt",
            "source_batch": "001",
            "quality_status": review["status"],
        })

    ids = [str(row["id"]) for row in merged]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate IDs in merged dataset.")

    warnings = []

    for i, first in enumerate(merged):
        for second in merged[i + 1:]:
            if first["language"] != second["language"]:
                continue

            left = normalize(first["user_message"])
            right = normalize(second["user_message"])

            similarity = difflib.SequenceMatcher(
                None, left, right
            ).ratio()

            if similarity >= 0.82:
                warnings.append({
                    "first_id": first["id"],
                    "second_id": second["id"],
                    "similarity": round(similarity, 3),
                    "first_prompt": first["user_message"],
                    "second_prompt": second["user_message"],
                })

    for row in merged:
        counts[row["language"]] += 1
        counts[f"tone:{row['tone']}"] += 1

    report = {
        "total": len(merged),
        "language_counts": {
            language: counts[language]
            for language in ("english", "tamil", "tanglish")
        },
        "tone_counts": {
            key.removeprefix("tone:"): count
            for key, count in sorted(counts.items())
            if key.startswith("tone:")
        },
        "near_duplicate_warnings": warnings,
        "source_hashes": {
            path.name: digest(path)
            for path in (
                BASE, BASE_REVIEWS, PROMPTS,
                CANDIDATES, BATCH_REVIEWS
            )
        },
        "status": (
            "Merged for further evaluation. "
            "Not yet approved for fine-tuning."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8") as file:
        for row in merged:
            file.write(
                json.dumps(row, ensure_ascii=False) + "\n"
            )

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 50)
    print("RIA-1 V2 DATASET")
    print("=" * 50)
    print("Total records:", len(merged))
    print("English:", counts["english"])
    print("Tamil:", counts["tamil"])
    print("Tanglish:", counts["tanglish"])
    print("Near-duplicate warnings:", len(warnings))
    print("Dataset:", OUTPUT)
    print("Report:", REPORT)
    print("Status: Further evaluation required")


if __name__ == "__main__":
    main()

