
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DATASET = ROOT / "ria1/data/standardized/ria1_v1.jsonl"
REVIEWS = ROOT / "ria1/data/audit/quality_reviews.json"

OUTPUT_DIR = ROOT / "ria1/data/training"

LANGUAGE_INSTRUCTIONS = {
    "english": (
        "Respond in natural conversational English."
    ),
    "tamil": (
        "தமிழில் இயல்பாக, அன்றாடம் பேசுவது போல பதில் சொல். "
        "தேவையில்லாமல் முறையான தமிழ் பயன்படுத்தாதே."
    ),
    "tanglish": (
        "Respond in natural spoken Tamil written using "
        "English letters. Mix English words naturally. "
        "Use real Tamil grammar, not invented Tamil words. "
        "Do not use Tamil script."
    ),
}

TONE_INSTRUCTIONS = {
    "casual_friendly": "Sound relaxed and friendly.",
    "confused_learning": "Explain simply and accurately.",
    "sad_stressed": "Respond gently and supportively.",
    "happy_excited": "Be playful and enthusiastic.",
    "frustrated_angry": (
        "Be calm and acknowledge errors when responsible."
    ),
    "romantic_flirty": (
        "Be playful and lightly flirty when invited, "
        "without pretending to be human."
    ),
    "lonely_vulnerable": (
        "Be attentive and warm without encouraging dependency."
    ),
    "neutral": (
        "Respond naturally without assuming a strong emotion."
    ),
}


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def read_jsonl(path):
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if line.strip():
                record = json.loads(line)

                if not isinstance(record, dict):
                    raise ValueError(
                        f"Invalid record at line {line_number}"
                    )

                records.append(record)

    return records


def main():
    records = read_jsonl(DATASET)

    review_data = json.loads(
        REVIEWS.read_text(encoding="utf-8")
    )
    reviews = review_data["reviews_by_id"]

    record_ids = [str(item["id"]) for item in records]

    if len(record_ids) != len(set(record_ids)):
        raise ValueError("Duplicate dataset IDs.")

    if set(record_ids) != set(reviews):
        raise ValueError(
            "Dataset and quality-review IDs do not match."
        )

    exported = []
    counts = Counter()

    for record in records:
        record_id = str(record["id"])
        review = reviews[record_id]
        status = review["status"]

        if status not in {"approved", "edited_approved"}:
            continue

        language = record["language"]
        tone = record["tone"]

        if language not in LANGUAGE_INSTRUCTIONS:
            raise ValueError(
                f"Invalid language: {language}"
            )

        if tone not in TONE_INSTRUCTIONS:
            raise ValueError(
                f"Invalid tone: {tone}"
            )

        user = record["user_message"]

        response = (
            review.get("corrected_response")
            if status == "edited_approved"
            else record["assistant_response"]
        )

        if not isinstance(user, str) or not user.strip():
            raise ValueError(
                f"Missing user message: {record_id}"
            )

        if not isinstance(response, str) or not response.strip():
            raise ValueError(
                f"Missing approved response: {record_id}"
            )

        system = (
            "You are Ria, a conversational AI companion. "
            "Be helpful, accurate, natural and emotionally aware. "
            "Never invent personal memories or real-world experiences. "
            + LANGUAGE_INSTRUCTIONS[language]
            + " "
            + TONE_INSTRUCTIONS[tone]
        )

        exported.append({
            "messages": [
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": user.strip(),
                },
                {
                    "role": "assistant",
                    "content": response.strip(),
                },
            ]
        })

        counts[language] += 1
        counts[f"tone:{tone}"] += 1

    if not exported:
        raise ValueError("No approved examples to export.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset_path = OUTPUT_DIR / "ria1_sft_v1.jsonl"
    manifest_path = OUTPUT_DIR / "manifest_v1.json"

    with dataset_path.open(
        "w", encoding="utf-8"
    ) as file:
        for example in exported:
            file.write(
                json.dumps(
                    example,
                    ensure_ascii=False,
                )
                + "\n"
            )

    manifest = {
        "schema_version": "1.0",
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source": str(DATASET),
        "source_sha256": sha256_file(DATASET),
        "quality_reviews_sha256": sha256_file(REVIEWS),
        "training_export": str(dataset_path),
        "training_export_sha256": sha256_file(
            dataset_path
        ),
        "total_examples": len(exported),
        "language_counts": {
            language: counts[language]
            for language in LANGUAGE_INSTRUCTIONS
        },
        "tone_counts": {
            tone: counts[f"tone:{tone}"]
            for tone in TONE_INSTRUCTIONS
        },
        "held_out_evaluation": (
            "evaluation/personality_prompts.json"
        ),
        "notes": [
            "All exported responses received human review.",
            "No generated responses were automatically approved.",
            "No fine-tuning has been performed.",
            "The dataset is a pilot, not sufficient for production training.",
            "License and provenance clearance remain required.",
        ],
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 50)
    print("RIA-1 TRAINING EXPORT")
    print("=" * 50)

    print("Exported:", len(exported))
    print("English:", counts["english"])
    print("Tamil:", counts["tamil"])
    print("Tanglish:", counts["tanglish"])

    print("\nDATASET")
    print(dataset_path)

    print("\nMANIFEST")
    print(manifest_path)

    print("\nSHA256")
    print(manifest["training_export_sha256"])

    print("\nSTATUS")
    print("Pilot dataset exported. Model training not started.")


if __name__ == "__main__":
    main()

