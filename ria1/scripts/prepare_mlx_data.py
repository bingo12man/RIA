
import json
import hashlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "ria1/data/standardized/ria1_v2_deduplicated.jsonl"
OUT = ROOT / "ria1/data/mlx_pilot"

LANGUAGE_RULES = {
    "english": "Reply in natural English.",
    "tamil": "Reply in conversational Tamil script.",
    "tanglish": (
        "Reply in natural spoken Tamil written with "
        "English letters, mixing English words naturally."
    ),
}

TONE_RULES = {
    "casual_friendly": "Be relaxed and friendly.",
    "confused_learning": "Explain simply and accurately.",
    "sad_stressed": "Be gentle and understanding.",
    "happy_excited": "Be cheerful and playful.",
    "frustrated_angry": "Acknowledge mistakes calmly.",
    "romantic_flirty": "Be lightly playful when invited.",
    "lonely_vulnerable": "Be warm and attentive.",
    "neutral": "Do not assume a strong emotion.",
}


def to_chat(record):
    language = record["language"]
    tone = record["tone"]

    system = (
        "You are Ria, a helpful, emotionally aware "
        "AI companion. Respond to the user's actual "
        "request. Never invent personal experiences. "
        + LANGUAGE_RULES[language]
        + " "
        + TONE_RULES[tone]
    )

    return {
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": record["user_message"],
            },
            {
                "role": "assistant",
                "content": record["assistant_response"],
            },
        ]
    }


def normalized(text):
    return " ".join(text.casefold().split())


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False)
                + "\n"
            )


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rows = [
        json.loads(line)
        for line in SOURCE.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    assert len(rows) == 61, (
        "Expected 61 deduplicated records. "
        "Check your source dataset."
    )

    train = []
    valid = []

    train_raw = []
    valid_raw = []

    for row in rows:
        if row["review_status"] != "approved":
            raise ValueError(
                f"Unapproved record: {row['id']}"
            )

        chat = to_chat(row)

        if row.get("source_batch") == "001":
            valid.append(chat)
            valid_raw.append(row)
        else:
            train.append(chat)
            train_raw.append(row)

    assert len(train) == 40, len(train)
    assert len(valid) == 21, len(valid)

    # Compare exact prompts across sets.
    train_prompts = {
        normalized(r["user_message"])
        for r in train_raw
    }

    valid_prompts = {
        normalized(r["user_message"])
        for r in valid_raw
    }

    overlap = train_prompts & valid_prompts

    if overlap:
        raise ValueError(
            f"Exact prompt overlap: {sorted(overlap)}"
        )

    OUT.mkdir(parents=True, exist_ok=True)

    train_path = OUT / "train.jsonl"
    valid_path = OUT / "valid.jsonl"

    write_jsonl(train_path, train)
    write_jsonl(valid_path, valid)

    report = {
        "train_count": len(train),
        "valid_count": len(valid),
        "train_languages": dict(Counter(
            r["language"] for r in train_raw
        )),
        "valid_languages": dict(Counter(
            r["language"] for r in valid_raw
        )),
        "train_sha256": sha256(train_path),
        "valid_sha256": sha256(valid_path),
        "validation_ids": [
            r["id"] for r in valid_raw
        ],
        "notes": [
            "Entire Batch 001 reserved for validation.",
            "No exact prompt overlap detected.",
            "Semantic overlap requires manual review.",
            "This is a small engineering pilot.",
            "Not sufficient for production-quality claims.",
        ],
    }

    (OUT / "split_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nRIA-1 MLX DATA PREPARATION")
    print("=" * 45)
    print("Training:", len(train))
    print("Validation:", len(valid))
    print("Training languages:", report["train_languages"])
    print("Validation languages:", report["valid_languages"])
    print("Exact prompt overlap:", len(overlap))
    print("Saved:", OUT)


if __name__ == "__main__":
    main()

