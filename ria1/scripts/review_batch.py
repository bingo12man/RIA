
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCE = (
    ROOT / "ria1/data/expansion/"
    "batch_001_candidates.jsonl"
)

REVIEWS = (
    ROOT / "ria1/data/expansion/"
    "batch_001_reviews.json"
)


def load_candidates():
    with SOURCE.open("r", encoding="utf-8") as file:
        rows = [
            json.loads(line)
            for line in file
            if line.strip()
        ]

    ids = [str(r["id"]) for r in rows]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate candidate IDs")

    return rows


def save_json_atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")

    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tmp.replace(path)


def main():
    candidates = load_candidates()

    if REVIEWS.exists():
        state = json.loads(
            REVIEWS.read_text(encoding="utf-8")
        )
    else:
        state = {
            "schema_version": "1.0",
            "batch": "001",
            "reviews_by_id": {},
        }

    reviews = state["reviews_by_id"]

    print("\n" + "=" * 55)
    print("RIA-1 BATCH 001 HUMAN REVIEW")
    print("=" * 55)
    print("a = approve candidate")
    print("e = edit candidate and approve")
    print("r = reject candidate")
    print("s = skip")
    print("q = save and quit")

    for index, item in enumerate(candidates, 1):
        record_id = str(item["id"])

        if record_id in reviews:
            continue

        if item.get("candidate_status") != "pending_review":
            print("Skipping failed generation:", record_id)
            continue

        print("\n" + "-" * 55)
        print(f"{index}/{len(candidates)} — {record_id}")
        print("LANGUAGE:", item["language"])
        print("TONE:", item["tone"])

        print("\nUSER:")
        print(item["user_message"])

        print("\nRIA CANDIDATE:")
        print(item["candidate_response"])

        while True:
            choice = input(
                "\nApprove [a], edit [e], reject [r], "
                "skip [s], quit [q]: "
            ).strip().lower()

            if choice in ("a", "e", "r", "s", "q"):
                break

            print("Invalid choice")

        if choice == "q":
            save_json_atomic(REVIEWS, state)
            print("Saved:", REVIEWS)
            return

        if choice == "s":
            continue

        corrected = None
        note = ""

        if choice == "e":
            corrected = input(
                "Write corrected response (single line): "
            ).strip()

            if not corrected:
                print("No correction entered. Skipped.")
                continue

        if choice == "r":
            note = input(
                "Why reject? "
            ).strip()

        reviews[record_id] = {
            "status": {
                "a": "approved",
                "e": "edited_approved",
                "r": "rejected",
            }[choice],
            "corrected_response": corrected,
            "note": note,
            "reviewed_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        save_json_atomic(REVIEWS, state)
        print("Saved:", reviews[record_id]["status"])

    counts = Counter(
        item["status"]
        for item in reviews.values()
    )

    print("\n" + "=" * 55)
    print("RIA-1 BATCH 001 REVIEW SUMMARY")
    print("=" * 55)
    print("Candidates:", len(candidates))
    print("Reviewed:", len(reviews))
    print("Approved:", counts["approved"])
    print(
        "Edited and approved:",
        counts["edited_approved"]
    )
    print("Rejected:", counts["rejected"])
    print(
        "Remaining:",
        len(candidates) - len(reviews)
    )
    print("Review file:", REVIEWS)


if __name__ == "__main__":
    main()

