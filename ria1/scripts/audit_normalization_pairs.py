
import json
import hashlib
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]

SOURCE = (
    ROOT / "ria1/data/releases/language_foundation_v1/"
    "meaning_reference.jsonl"
)

OUTPUT = (
    ROOT / "ria1/data/evaluation/"
    "normalization_pair_audit_v1.json"
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Audit already exists: {OUTPUT}"
        )

    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    rows = []

    for line in SOURCE.read_text(
        encoding="utf-8"
    ).splitlines():
        if line.strip():
            rows.append(json.loads(line))

    complete = []
    missing = []
    categories = Counter()

    print("\nRIA-1 — MODULE 4.56")
    print("NORMALIZATION PAIR AUDIT")
    print("=" * 65)

    for index, row in enumerate(rows, 1):
        tanglish = str(row.get("tanglish") or "").strip()
        tamil = str(row.get("tamil_equivalent") or "").strip()

        if not tanglish or not tamil:
            missing.append(index)
            continue

        categories["candidate_pair"] += 1

        complete.append({
            "source_index": index,
            "tanglish": tanglish,
            "tamil": tamil,
            "review_status": "pending",
            "pair_type": "unclassified",
        })

    report = {
        "module": "4.56",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": sha256(SOURCE),
        "total_source_records": len(rows),
        "candidate_pairs": len(complete),
        "missing_pair_indices": missing,
        "approved_for_training": 0,
        "status": "requires_pair_level_review",
        "limitations": [
            "Existing Tamil equivalents may paraphrase.",
            "Some examples may normalize vocabulary.",
            "Pair quality has not been independently verified.",
            "Do not train before approving pair types.",
            "Frozen evaluation examples must remain excluded.",
        ],
        "pairs": complete,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8",
    )

    print("Source records:", len(rows))
    print("Candidate pairs:", len(complete))
    print("Missing pairs:", len(missing))
    print("Training-approved:", 0)

    print("\nFIRST FIVE CANDIDATES")

    for row in complete[:5]:
        print("\nTanglish:", row["tanglish"])
        print("Tamil:", row["tamil"])

    print("\nSaved:", OUTPUT)
    print("Status: Human pair review required")


if __name__ == "__main__":
    main()

