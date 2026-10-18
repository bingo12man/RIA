
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "ria1/data/standardized/ria1_v1.jsonl"
OUTPUT = ROOT / "ria1/data/audit/quality_reviews.json"

FLAGS = [
    "unnatural_language",
    "wrong_tone",
    "factual_error",
    "wrong_perspective",
    "repetitive",
    "incomplete",
    "privacy_or_safety",
    "other",
]


def load_records():
    records = []

    with SOURCE.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))

    ids = [str(record["id"]) for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate record IDs found.")

    return records


def save(data):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".tmp")

    with temp.open("w", encoding="utf-8") as file:
        json.dump(
            data, file, ensure_ascii=False, indent=2
        )

    temp.replace(OUTPUT)


def main():
    records = load_records()

    if OUTPUT.exists():
        state = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        state = {
            "schema_version": "1.0",
            "reviews_by_id": {},
        }

    reviews = state.setdefault("reviews_by_id", {})

    print("\n" + "=" * 60)
    print("RIA-1 CONVERSATION QUALITY REVIEW")
    print("=" * 60)
    print("a = approve response")
    print("e = edit response and approve")
    print("r = reject response")
    print("s = skip")
    print("q = save and quit")
    print("=" * 60)

    for index, record in enumerate(records, 1):
        record_id = str(record["id"])

        if record_id in reviews:
            continue

        print("\n" + "-" * 60)
        print(f"Conversation {index}/{len(records)}")
        print("ID:", record_id)
        print("Language:", record["language"])
        print("Tone:", record["tone"])

        print("\nUSER:")
        print(record["user_message"])

        print("\nRIA:")
        print(record["assistant_response"])

        while True:
            choice = input(
                "\nApprove [a], edit [e], reject [r], "
                "skip [s], quit [q]: "
            ).strip().lower()

            if choice in {"a", "e", "r", "s", "q"}:
                break

            print("Invalid option.")

        if choice == "q":
            save(state)
            print("Progress saved.")
            return

        if choice == "s":
            continue

        status = {
            "a": "approved",
            "e": "edited_approved",
            "r": "rejected",
        }[choice]

        corrected = None
        flags = []
        note = ""

        if choice == "e":
            print(
                "\nEnter your corrected response "
                "on one line:"
            )
            corrected = input("Corrected RIA: ").strip()

            if not corrected:
                print("Empty correction; skipped.")
                continue

        if choice in {"e", "r"}:
            print("\nIssue flags:")
            for number, flag in enumerate(FLAGS, 1):
                print(f"  {number}. {flag}")

            raw_flags = input(
                "Flag numbers (comma separated, "
                "or Enter to skip): "
            ).strip()

            if raw_flags:
                try:
                    numbers = [
                        int(n.strip())
                        for n in raw_flags.split(",")
                    ]

                    if any(
                        n < 1 or n > len(FLAGS)
                        for n in numbers
                    ):
                        raise ValueError

                    flags = [
                        FLAGS[n - 1]
                        for n in dict.fromkeys(numbers)
                    ]

                except ValueError:
                    print("Invalid flags; skipped.")
                    continue

            note = input(
                "Optional review note: "
            ).strip()

        reviews[record_id] = {
            "status": status,
            "corrected_response": corrected,
            "flags": flags,
            "note": note,
            "reviewed_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        save(state)
        print("Saved review:", status)

    counts = Counter(
        review["status"]
        for review in reviews.values()
    )

    print("\n" + "=" * 60)
    print("RIA-1 QUALITY REVIEW SUMMARY")
    print("=" * 60)
    print("Total records:", len(records))
    print("Reviewed:", len(reviews))
    print("Approved:", counts["approved"])
    print("Edited and approved:", counts["edited_approved"])
    print("Rejected:", counts["rejected"])
    print("Remaining:", len(records) - len(reviews))
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()

