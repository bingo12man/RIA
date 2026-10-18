
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE = (
    ROOT / "ria1/data/evaluation/"
    "normalization_pair_audit_v1.json"
)

REVIEWS = (
    ROOT / "ria1/data/evaluation/"
    "normalization_pair_reviews_v1.json"
)

EXPORT = (
    ROOT / "ria1/data/evaluation/"
    "approved_normalization_pairs_v1.jsonl"
)


def digest(data):
    encoded = json.dumps(
        data, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def save_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    temp.replace(path)


def load_state(source_hash):
    if REVIEWS.exists():
        state = json.loads(
            REVIEWS.read_text(encoding="utf-8")
        )

        if state["source_hash"] != source_hash:
            raise ValueError(
                "Source audit changed after review started."
            )

        return state

    return {
        "source_hash": source_hash,
        "reviews": {}
    }


def review_pair(index, total, pair):
    print("\n" + "=" * 65)
    print(f"{index}/{total}")
    print("TANGLISH:", pair["tanglish"])
    print("TAMIL:   ", pair["tamil"])

    print("\n1 = Faithful script conversion")
    print("2 = Meaning-preserving normalization")
    print("3 = Incorrect; enter corrected Tamil")
    print("s = Skip")
    print("q = Save and quit")

    while True:
        choice = input("Decision [1/2/3/s/q]: ").strip().lower()

        if choice in ("1", "2"):
            return {
                "status": "approved",
                "type": (
                    "faithful_script"
                    if choice == "1"
                    else "normalization"
                ),
                "tamil": pair["tamil"],
            }

        if choice == "3":
            correction = input(
                "Correct Tamil sentence: "
            ).strip()

            if not correction:
                print("Correction cannot be empty.")
                continue

            return {
                "status": "approved_corrected",
                "type": "corrected",
                "tamil": correction,
            }

        if choice == "s":
            return None

        if choice == "q":
            return "quit"

        print("Invalid choice.")


def main():
    audit = json.loads(
        SOURCE.read_text(encoding="utf-8")
    )

    pairs = audit["pairs"]
    assert len(pairs) == 124

    source_hash = digest(pairs)
    state = load_state(source_hash)
    reviews = state["reviews"]

    print("\nRIA-1 — MODULE 4.57")
    print("NORMALIZATION PAIR REVIEW")
    print("=" * 65)

    for index, pair in enumerate(pairs, 1):
        rid = str(pair["source_index"])

        if rid in reviews:
            continue

        decision = review_pair(
            index, len(pairs), pair
        )

        if decision == "quit":
            break

        if decision is None:
            continue

        decision["reviewed_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        reviews[rid] = decision
        save_json(REVIEWS, state)

        print("Saved.")

    counts = Counter(
        row["type"] for row in reviews.values()
    )

    print("\n" + "=" * 65)
    print("REVIEW SUMMARY")
    print("Reviewed:", len(reviews), "/", len(pairs))
    print("Faithful:", counts["faithful_script"])
    print("Normalized:", counts["normalization"])
    print("Corrected:", counts["corrected"])
    print("Remaining:", len(pairs) - len(reviews))

    if len(reviews) != len(pairs):
        print("\nRun again to review remaining examples.")
        return

    if EXPORT.exists():
        print("\nExport already exists; refusing overwrite.")
        return

    with EXPORT.open("x", encoding="utf-8") as f:
        for pair in pairs:
            rid = str(pair["source_index"])
            decision = reviews[rid]

            row = {
                "id": f"RIA-NORM-{int(rid):03d}",
                "tanglish": pair["tanglish"],
                "tamil": decision["tamil"],
                "pair_type": decision["type"],
                "review_status": "approved",
            }

            f.write(
                json.dumps(row, ensure_ascii=False)
                + "\n"
            )

    print("\nALL 124 PAIRS REVIEWED")
    print("Exported:", EXPORT)
    print("Status: Approved dataset candidate")


if __name__ == "__main__":
    main()

