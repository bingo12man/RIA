
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "training/data/original/approved_conversations.jsonl"
REVIEWS = ROOT / "ria1/data/audit/legacy_tone_reviews.json"
OUTPUT = ROOT / "ria1/data/standardized/ria1_v1.jsonl"
REPORT = ROOT / "ria1/data/audit/ria1_v1_report.json"

LANGUAGES = {"english", "tamil", "tanglish"}

TONES = {
    "casual_friendly",
    "confused_learning",
    "sad_stressed",
    "happy_excited",
    "frustrated_angry",
    "romantic_flirty",
    "lonely_vulnerable",
    "neutral",
}


def extract_pair(record):
    messages = record.get("messages")

    if isinstance(messages, list):
        users = [
            m.get("content", "")
            for m in messages
            if isinstance(m, dict)
            and m.get("role") == "user"
        ]

        assistants = [
            m.get("content", "")
            for m in messages
            if isinstance(m, dict)
            and m.get("role") == "assistant"
        ]

        if len(users) == 1 and len(assistants) == 1:
            return users[0], assistants[0]

        return None, None

    return (
        record.get("user_message")
        or record.get("user")
        or record.get("prompt"),
        record.get("assistant_response")
        or record.get("assistant")
        or record.get("response"),
    )


def main():
    reviews_data = json.loads(
        REVIEWS.read_text(encoding="utf-8")
    )

    reviews = reviews_data["reviews_by_source_line"]

    records = []
    issues = []
    counts = Counter()
    seen_ids = set()

    for line_number, line in enumerate(
        SOURCE.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        original = json.loads(line)
        source_id = str(
            original.get("id") or f"source-line-{line_number}"
        )

        user, assistant = extract_pair(original)
        language = str(
            original.get("language") or ""
        ).lower().strip()

        original_tone = str(
            original.get("tone") or ""
        ).lower().strip()

        review_status = str(
            original.get("review_status")
            or original.get("status")
            or ""
        ).lower().strip()

        tone = original_tone
        tone_review = "existing_label"

        if original_tone == "unlabeled":
            decision = reviews.get(str(line_number))

            if (
                not isinstance(decision, dict)
                or decision.get("review_status") != "human_approved"
                or decision.get("record_id") != source_id
            ):
                issues.append(
                    f"Line {line_number}: missing or mismatched tone review"
                )
                continue

            tone = decision.get("approved_tone")
            tone_review = "human_reviewed_legacy"

        if (
            language not in LANGUAGES
            or tone not in TONES
            or review_status != "approved"
            or not isinstance(user, str)
            or not user.strip()
            or not isinstance(assistant, str)
            or not assistant.strip()
            or source_id in seen_ids
        ):
            issues.append(
                f"Line {line_number}: invalid or duplicate record"
            )
            continue

        seen_ids.add(source_id)

        record = {
            "id": source_id,
            "language": language,
            "tone": tone,
            "user_message": user.strip(),
            "assistant_response": assistant.strip(),
            "review_status": "approved",
            "tone_review": tone_review,
            "source_line": line_number,
            "source": "existing_ria_dataset",
        }

        records.append(record)
        counts[language] += 1
        counts[f"{language}/{tone}"] += 1

    if issues:
        print("Dataset validation failed:")
        for issue in issues:
            print("-", issue)

        print("No new dataset was written.")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    report = {
        "total": len(records),
        "language_counts": {
            lang: counts[lang] for lang in sorted(LANGUAGES)
        },
        "language_tone_counts": {
            key: value
            for key, value in sorted(counts.items())
            if "/" in key
        },
        "tone_labels": sorted(TONES),
        "training_ready": False,
        "note": (
            "Tone metadata merged. Content quality, provenance, "
            "data splits and training approval remain pending."
        ),
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nRIA-1 V1 DATASET")
    print("=" * 45)
    print("Total:", len(records))
    print("English:", counts["english"])
    print("Tamil:", counts["tamil"])
    print("Tanglish:", counts["tanglish"])
    print("Validation errors:", len(issues))
    print("Dataset:", OUTPUT)
    print("Report:", REPORT)
    print("Training ready: No — content review pending")


if __name__ == "__main__":
    main()

