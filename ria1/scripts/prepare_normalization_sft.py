
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ria1/data/normalization_training_v2"
DEST = ROOT / "ria1/data/mlx_normalization_v1"

SYSTEM = (
    "Convert conversational Tanglish into natural Tamil script. "
    "Preserve the exact meaning, pronouns, negation, tense, "
    "requests, questions, quantities and English technical names. "
    "Do not answer, explain, or translate into English. "
    "Return only the Tamil-script sentence."
)


def load(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert(row):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": row["tanglish"]},
            {"role": "assistant", "content": row["tamil"]},
        ]
    }


def main():
    if DEST.exists():
        raise FileExistsError(
            f"Output already exists: {DEST}"
        )

    train = load(SOURCE / "train.jsonl")
    valid = load(SOURCE / "valid.jsonl")
    flagged = load(SOURCE / "flagged.jsonl")

    if len(train) != 99 or len(valid) != 25 or flagged:
        raise ValueError(
            "Expected 99 training, 25 validation, "
            "and zero flagged examples."
        )

    train_ids = {r["id"] for r in train}
    valid_ids = {r["id"] for r in valid}

    if len(train_ids) != 99 or len(valid_ids) != 25:
        raise ValueError("Duplicate IDs detected")

    if train_ids & valid_ids:
        raise ValueError("Training/validation leakage")

    DEST.mkdir(parents=True, exist_ok=False)

    for filename, rows in [
        ("train.jsonl", train),
        ("valid.jsonl", valid),
    ]:
        with (DEST / filename).open(
            "x", encoding="utf-8"
        ) as file:
            for row in rows:
                file.write(
                    json.dumps(
                        convert(row), ensure_ascii=False
                    ) + "\n"
                )

    manifest = {
        "module": "4.61",
        "training_examples": len(train),
        "validation_examples": len(valid),
        "system_prompt": SYSTEM,
        "source_train_sha256": sha256(
            SOURCE / "train.jsonl"
        ),
        "source_valid_sha256": sha256(
            SOURCE / "valid.jsonl"
        ),
        "mlx_train_sha256": sha256(
            DEST / "train.jsonl"
        ),
        "mlx_valid_sha256": sha256(
            DEST / "valid.jsonl"
        ),
        "status": "prepared_not_trained",
        "limitations": [
            "Only 99 training examples.",
            "Validation contains 25 examples.",
            "Fine-tuning may overfit.",
            "A fresh untouched benchmark is required.",
        ],
    }

    (DEST / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8"
    )

    print("\nRIA-1 — MODULE 4.61")
    print("=" * 50)
    print("Training:", len(train))
    print("Validation:", len(valid))
    print("Format: chat messages")
    print("Output:", DEST)
    print("Status: Ready for baseline and training setup")


if __name__ == "__main__":
    main()

