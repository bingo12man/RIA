
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "ria1/data/evaluation"

SOURCE = BASE / "approved_normalization_pairs_v1.jsonl"
OUTPUT = BASE / "approved_normalization_pairs_v2.jsonl"

TARGET = "RIA-NORM-107"
PROPOSED = "FastAPI யூஸ் பண்றேன், டேட்டாபேஸ் MongoDB."


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Corrected dataset already exists: {OUTPUT}"
        )

    rows = [
        json.loads(line)
        for line in SOURCE.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    matches = [r for r in rows if r["id"] == TARGET]

    if len(matches) != 1:
        raise ValueError("Expected exactly one RIA-NORM-107")

    row = matches[0]

    print("\nRIA-1 — MODULE 4.59")
    print("=" * 55)
    print("ID:", TARGET)
    print("Tanglish:", row["tanglish"])
    print("Existing Tamil:", row["tamil"])
    print("Proposed Tamil:", PROPOSED)

    print("\nReview the proposed correction.")
    answer = input("Approve? [y/edit/q]: ").strip().lower()

    if answer == "q":
        return

    if answer == "edit":
        corrected = input("Correct Tamil: ").strip()
    elif answer == "y":
        corrected = PROPOSED
    else:
        print("No changes made.")
        return

    if not corrected:
        raise ValueError("Correction cannot be empty")

    if not any("\u0b80" <= c <= "\u0bff" for c in corrected):
        raise ValueError("Correction must contain Tamil script")

    row["tamil"] = corrected
    row["pair_type"] = "corrected"
    row["review_status"] = "approved"

    with OUTPUT.open("x", encoding="utf-8") as f:
        for item in rows:
            f.write(
                json.dumps(item, ensure_ascii=False) + "\n"
            )

    print("\nSaved:", OUTPUT)
    print("Records:", len(rows))
    print("Original approved dataset remains unchanged.")


if __name__ == "__main__":
    main()

