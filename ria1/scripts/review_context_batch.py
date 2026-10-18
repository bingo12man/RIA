
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE = (
    ROOT / "ria1/data/language_foundation/"
    "context_switching_001.jsonl"
)
OUTPUT = (
    ROOT / "ria1/data/language_foundation/"
    "context_switching_001_reviews.json"
)


def save(state):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".tmp")
    temp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(OUTPUT)


def main():
    rows = [
        json.loads(line)
        for line in SOURCE.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    if OUTPUT.exists():
        state = json.loads(
            OUTPUT.read_text(encoding="utf-8")
        )
    else:
        state = {"reviews_by_id": {}}

    reviews = state["reviews_by_id"]

    for index, row in enumerate(rows, 1):
        record_id = row["id"]

        if record_id in reviews:
            continue

        print("\n" + "=" * 55)
        print(f"RECORD {index}/{len(rows)} — {record_id}")
        print("PREVIOUS USER:", row["previous_user"])
        print("PREVIOUS RIA:", row["previous_ria"])
        print("USER:", row["user_message"])
        print("SUGGESTED MEANING:", row["english_meaning"])

        choice = input(
            "\nReview [Enter], reject [r], "
            "skip [s], quit [q]: "
        ).strip().lower()

        if choice == "q":
            save(state)
            return

        if choice == "s":
            continue

        if choice == "r":
            reviews[record_id] = {
                "status": "rejected",
                "reviewed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }
            save(state)
            continue

        if choice != "":
            print("Invalid selection; skipped.")
            continue

        meaning = input(
            "Correct English meaning "
            "[Enter to accept suggestion]: "
        ).strip() or row["english_meaning"]

        tamil = input(
            "Natural Tamil equivalent: "
        ).strip()

        response = input(
            "Natural Ria Tanglish response: "
        ).strip()

        if not tamil or not response:
            print("Missing Tamil or response. Skipped.")
            continue

        confirm = input(
            "Approve this complete record? [y/N]: "
        ).strip().lower()

        if confirm != "y":
            print("Not approved.")
            continue

        reviews[record_id] = {
            "status": "approved",
            "english_meaning": meaning,
            "tamil_equivalent": tamil,
            "ria_response": response,
            "reviewed_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        save(state)
        print("Saved.")

    approved = sum(
        r["status"] == "approved"
        for r in reviews.values()
    )

    print("\nRIA-1 LANGUAGE REVIEW SUMMARY")
    print("=" * 45)
    print("Total:", len(rows))
    print("Reviewed:", len(reviews))
    print("Approved:", approved)
    print("Rejected:", len(reviews) - approved)
    print("Remaining:", len(rows) - len(reviews))
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()

