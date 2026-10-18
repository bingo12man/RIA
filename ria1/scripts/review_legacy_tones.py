
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCE = (
    ROOT / "training/data/original/"
    "approved_conversations.jsonl"
)

SUGGESTIONS = (
    ROOT / "ria1/data/audit/"
    "legacy_tone_suggestions.json"
)

DECISIONS = (
    ROOT / "ria1/data/audit/"
    "legacy_tone_reviews.json"
)

TONES = [
    "casual_friendly",
    "confused_learning",
    "sad_stressed",
    "happy_excited",
    "frustrated_angry",
    "romantic_flirty",
    "lonely_vulnerable",
    "neutral",
]


def load_json(path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temporary.replace(path)


def extract_pair(record):
    messages = record.get("messages")

    if isinstance(messages, list):
        users = [
            m.get("content")
            for m in messages
            if isinstance(m, dict)
            and m.get("role") == "user"
        ]

        assistants = [
            m.get("content")
            for m in messages
            if isinstance(m, dict)
            and m.get("role") == "assistant"
        ]

        if len(users) == 1 and len(assistants) == 1:
            return users[0], assistants[0]

        return None, None

    user = (
        record.get("user_message")
        or record.get("user")
        or record.get("prompt")
    )

    assistant = (
        record.get("assistant_response")
        or record.get("assistant")
        or record.get("response")
    )

    return user, assistant


def load_records():
    result = {}

    with SOURCE.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue

            record = json.loads(line)

            if record.get("tone") != "unlabeled":
                continue

            user, assistant = extract_pair(record)

            result[str(line_number)] = {
                "id": str(
                    record.get("id")
                    or f"source-line-{line_number}"
                ),
                "user": user,
                "assistant": assistant,
            }

    return result


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    if not SUGGESTIONS.exists():
        raise FileNotFoundError(
            "Create legacy_tone_suggestions.json first."
        )

    suggestions_data = load_json(SUGGESTIONS, {})

    suggestions = suggestions_data.get(
        "suggestions_by_source_line", {}
    )

    if not isinstance(suggestions, dict):
        raise ValueError("Suggestions must be an object.")

    records = load_records()

    state = load_json(
        DECISIONS,
        {
            "schema_version": "1.0",
            "reviews_by_source_line": {},
        },
    )

    reviews = state.setdefault(
        "reviews_by_source_line", {}
    )

    print("\n" + "=" * 60)
    print("RIA-1 LEGACY TONE REVIEW")
    print("=" * 60)
    print("Enter = approve suggested tone")
    print("1-8   = select a different tone")
    print("s     = skip this conversation")
    print("q     = save and quit")
    print("=" * 60)

    for index, (line_number, record) in enumerate(
        records.items(), 1
    ):
        if line_number in reviews:
            continue

        suggestion = suggestions.get(
            line_number, "neutral"
        )

        if suggestion not in TONES:
            print(
                "Invalid suggestion on line",
                line_number,
                "- skipping"
            )
            continue

        if not record["user"] or not record["assistant"]:
            print(
                "Missing user or assistant text on line",
                line_number,
                "- skipping"
            )
            continue

        print("\n" + "-" * 60)
        print(
            f"Conversation {index}/{len(records)} "
            f"| Source line {line_number}"
        )
        print("Record ID:", record["id"])

        print("\nUSER:")
        print(record["user"])

        print("\nRIA:")
        print(record["assistant"])

        print("\nSUGGESTED:", suggestion)

        print("\nAVAILABLE TONES")
        for number, tone in enumerate(TONES, 1):
            print(f"  {number}. {tone}")

        while True:
            choice = input(
                "\nApprove [Enter], change [1-8], "
                "skip [s], quit [q]: "
            ).strip().lower()

            if choice == "":
                selected = suggestion
                break

            if choice == "s":
                selected = None
                break

            if choice == "q":
                save_json(DECISIONS, state)
                print("\nSaved:", DECISIONS)
                print("You can resume later.")
                return

            if choice.isdigit():
                number = int(choice)

                if 1 <= number <= len(TONES):
                    selected = TONES[number - 1]
                    break

            print("Invalid choice. Try again.")

        if selected is None:
            print("Skipped; remains pending review.")
            continue

        reviews[line_number] = {
            "record_id": record["id"],
            "suggested_tone": suggestion,
            "approved_tone": selected,
            "review_status": "human_approved",
            "reviewed_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        save_json(DECISIONS, state)

        print("Approved:", selected)

    print("\n" + "=" * 60)
    print("REVIEW SUMMARY")
    print("=" * 60)
    print("Eligible records:", len(records))
    print(
        "Reviewed:",
        len(set(records) & set(reviews))
    )
    print(
        "Remaining:",
        len(set(records) - set(reviews))
    )
    print("Saved:", DECISIONS)


if __name__ == "__main__":
    main()

