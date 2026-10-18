
import hashlib
import json
import random
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "ria1/data/evaluation"

SOURCE = BASE / "approved_normalization_pairs_v1.jsonl"

OUTPUT = ROOT / "ria1/data/normalization_training_v1"

EVALUATIONS = [
    BASE / "generalization_v2_frozen/prompts.jsonl",
    BASE / "tanglish_comprehension_v1.jsonl",
]

SEED = 42
THRESHOLD = 0.78


def read_jsonl(path):
    if not path.exists():
        raise FileNotFoundError(path)

    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text):
    return " ".join(
        re.findall(r"\w+", text.casefold())
    )


def write_jsonl(path, records):
    with path.open("x", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(
                    record, ensure_ascii=False
                ) + "\n"
            )


def evaluation_sentences():
    references = []

    for path in EVALUATIONS:
        for row in read_jsonl(path):
            sentence = (
                row.get("user_message")
                or row.get("tanglish")
                or row.get("input")
            )

            if sentence:
                references.append({
                    "source": path.name,
                    "text": sentence,
                })

    return references


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Output directory already exists: {OUTPUT}"
        )

    rows = read_jsonl(SOURCE)

    if len(rows) != 124:
        raise ValueError(
            f"Expected 124 approved pairs, found {len(rows)}"
        )

    seen_ids = set()
    seen_inputs = set()

    valid = []
    flagged = []
    categories = Counter()

    references = evaluation_sentences()

    print("\nRIA-1 — MODULE 4.58")
    print("NORMALIZATION TRAINING DATA VALIDATION")
    print("=" * 60)

    for row in rows:
        rid = row.get("id")
        tanglish = str(row.get("tanglish", "")).strip()
        tamil = str(row.get("tamil", "")).strip()
        pair_type = row.get("pair_type")

        reasons = []

        if not rid or rid in seen_ids:
            reasons.append("missing_or_duplicate_id")

        seen_ids.add(rid)

        if not tanglish or not tamil:
            reasons.append("empty_pair")

        if tanglish and tanglish in seen_inputs:
            reasons.append("duplicate_input")

        seen_inputs.add(tanglish)

        if row.get("review_status") != "approved":
            reasons.append("not_approved")

        if pair_type not in (
            "faithful_script",
            "normalization",
            "corrected",
        ):
            reasons.append("unknown_pair_type")

        if not re.search(r"[\u0B80-\u0BFF]", tamil):
            reasons.append("missing_tamil_script")

        matches = []

        for reference in references:
            similarity = SequenceMatcher(
                None,
                normalize(tanglish),
                normalize(reference["text"]),
            ).ratio()

            if similarity >= THRESHOLD:
                matches.append({
                    "source": reference["source"],
                    "similarity": round(similarity, 3),
                    "existing": reference["text"],
                })

        if matches:
            reasons.append("evaluation_overlap")

        candidate = {
            "id": rid,
            "tanglish": tanglish,
            "tamil": tamil,
            "pair_type": pair_type,
        }

        if reasons:
            flagged.append({
                **candidate,
                "reasons": reasons,
                "matches": matches,
            })
        else:
            valid.append(candidate)
            categories[pair_type] += 1

    # Deduplicate and split by normalized input.
    # A fixed seed makes the split reproducible.
    rng = random.Random(SEED)
    rng.shuffle(valid)

    split = round(len(valid) * 0.8)

    train = valid[:split]
    validation = valid[split:]

    OUTPUT.mkdir(parents=True, exist_ok=False)

    write_jsonl(
        OUTPUT / "train.jsonl",
        train,
    )
    write_jsonl(
        OUTPUT / "valid.jsonl",
        validation,
    )
    write_jsonl(
        OUTPUT / "flagged.jsonl",
        flagged,
    )

    report = {
        "module": "4.58",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": sha256(SOURCE),
        "total_approved": len(rows),
        "training_candidates": len(valid),
        "train_count": len(train),
        "validation_count": len(validation),
        "flagged_count": len(flagged),
        "pair_types": dict(categories),
        "seed": SEED,
        "overlap_threshold": THRESHOLD,
        "checks": [
            "Record count",
            "Approval status",
            "Unique IDs",
            "Duplicate input detection",
            "Tamil script presence",
            "Known evaluation lexical overlap",
        ],
        "limitations": [
            "Lexical similarity does not detect all semantic overlap.",
            "The 80/20 split is not an independent unseen benchmark.",
            "No model fine-tuning has been performed.",
            "Flagged examples are excluded until reviewed.",
            "Approved pair quality depends on human review accuracy.",
        ],
    }

    (OUTPUT / "manifest.json").write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("Approved records:", len(rows))
    print("Usable candidates:", len(valid))
    print("Training:", len(train))
    print("Validation:", len(validation))
    print("Flagged:", len(flagged))
    print("Pair types:", dict(categories))
    print("Output:", OUTPUT)

    if flagged:
        print("\nFLAGGED EXAMPLES")
        for row in flagged[:15]:
            print(
                row["id"],
                row["reasons"],
                row["tanglish"],
            )

    print("\nSTATUS: Dataset prepared; model training not started")


if __name__ == "__main__":
    main()

