
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RELEASE = ROOT / "ria1/data/releases/language_foundation_v1"
SOURCE = RELEASE / "comprehension_candidates.jsonl"
MANIFEST = RELEASE / "manifest.json"

OUT = ROOT / "ria1/data/mlx_comprehension_v1"
SEED = 42

SYSTEM = (
    "You understand conversational Tamil written with "
    "English letters (Tanglish). Explain in one concise "
    "English sentence what the CURRENT USER means. "
    "Use conversation context when provided. "
    "Preserve pronouns, tense, negation and emotional meaning. "
    "Do not answer the user's request."
)


def load_jsonl(path):
    with path.open("r", encoding="utf-8") as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text):
    return " ".join(text.casefold().split())


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )


def make_example(record):
    messages = record["messages"]

    if [m["role"] for m in messages] != [
        "system", "user", "assistant"
    ]:
        raise ValueError(
            f"Unexpected comprehension format: {record['id']}"
        )

    user = messages[1]["content"]
    answer = messages[2]["content"]

    if not user.strip() or not answer.strip():
        raise ValueError(f"Empty example: {record['id']}")

    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": answer},
        ]
    }


def main():
    if OUT.exists():
        raise FileExistsError(
            f"Output already exists: {OUT}. "
            "Refusing to overwrite a split."
        )

    manifest = json.loads(
        MANIFEST.read_text(encoding="utf-8")
    )

    expected_hash = manifest["files"][
        "comprehension_candidates.jsonl"
    ]["sha256"]

    if sha256(SOURCE) != expected_hash:
        raise ValueError("Frozen release hash mismatch")

    records = load_jsonl(SOURCE)

    if len(records) != 124:
        raise ValueError(
            f"Expected 124 records, got {len(records)}"
        )

    ids = [str(r["id"]) for r in records]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate IDs")

    # Prevent exact input overlap across splits.
    # Group records with identical normalized inputs.
    groups = defaultdict(list)

    for record in records:
        key = normalize(
            record["messages"][1]["content"]
        )
        groups[key].append(record)

    category_groups = defaultdict(list)

    for group in groups.values():
        categories = {
            row["category"] for row in group
        }

        # Keep repeated inputs in one split even if
        # they appear in different categories.
        category = sorted(categories)[0]
        category_groups[category].append(group)

    rng = random.Random(SEED)

    train_records = []
    valid_records = []

    for category in sorted(category_groups):
        items = category_groups[category][:]
        rng.shuffle(items)

        # Around 20% of the grouped examples
        # per category are reserved for validation.
        valid_group_count = max(
            1, round(len(items) * 0.2)
        )

        for group in items[:valid_group_count]:
            valid_records.extend(group)

        for group in items[valid_group_count:]:
            train_records.extend(group)

    train_ids = {r["id"] for r in train_records}
    valid_ids = {r["id"] for r in valid_records}

    if train_ids & valid_ids:
        raise ValueError("ID leakage across splits")

    train_inputs = {
        normalize(r["messages"][1]["content"])
        for r in train_records
    }

    valid_inputs = {
        normalize(r["messages"][1]["content"])
        for r in valid_records
    }

    if train_inputs & valid_inputs:
        raise ValueError("Exact input leakage across splits")

    if len(train_records) + len(valid_records) != 124:
        raise ValueError("Records lost during splitting")

    train = [make_example(r) for r in train_records]
    valid = [make_example(r) for r in valid_records]

    OUT.mkdir(parents=True, exist_ok=False)

    train_path = OUT / "train.jsonl"
    valid_path = OUT / "valid.jsonl"

    write_jsonl(train_path, train)
    write_jsonl(valid_path, valid)

    report = {
        "release": "language_foundation_v1",
        "seed": SEED,
        "train_count": len(train),
        "valid_count": len(valid),
        "train_categories": dict(Counter(
            r["category"] for r in train_records
        )),
        "valid_categories": dict(Counter(
            r["category"] for r in valid_records
        )),
        "train_ids": sorted(train_ids),
        "valid_ids": sorted(valid_ids),
        "train_sha256": sha256(train_path),
        "valid_sha256": sha256(valid_path),
        "source_sha256": sha256(SOURCE),
        "held_out_benchmark": (
            "ria1/data/evaluation/"
            "tanglish_comprehension_v1.jsonl"
        ),
        "limitations": [
            "Exact split overlap checked.",
            "Semantic/paraphrase overlap not guaranteed absent.",
            "Existing held-out benchmark was not copied into data.",
            "Review validation examples for near-duplicates.",
            "This is a small experimental dataset.",
        ],
    }

    (OUT / "split_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nRIA-1 COMPREHENSION SFT PREPARATION")
    print("=" * 50)
    print("Training:", len(train))
    print("Validation:", len(valid))
    print("Train categories:", report["train_categories"])
    print("Valid categories:", report["valid_categories"])
    print("Exact overlap: 0")
    print("Output:", OUT)
    print("Training started: No")


if __name__ == "__main__":
    main()

