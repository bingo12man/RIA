
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCE_FILE = (
    ROOT / "training/data/original/"
    "approved_conversations.jsonl"
)

OUTPUT_DIR = ROOT / "ria1/data/audit"
STANDARD_DIR = ROOT / "ria1/data/standardized"

LANGUAGES = {"english", "tamil", "tanglish"}

TONES = {
    "sad_stressed",
    "happy_excited",
    "romantic_flirty",
    "casual_friendly",
    "confused_learning",
    "frustrated_angry",
    "lonely_vulnerable",
}

APPROVAL_VALUES = {"approved"}

USER_KEYS = ("user_message", "user", "prompt")
ASSISTANT_KEYS = (
    "assistant_response",
    "assistant",
    "response",
)


def first_text(record, keys):
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_messages(record):
    messages = record.get("messages")

    if isinstance(messages, list):
        users = [
            m.get("content")
            for m in messages
            if isinstance(m, dict)
            and m.get("role") == "user"
            and isinstance(m.get("content"), str)
        ]

        assistants = [
            m.get("content")
            for m in messages
            if isinstance(m, dict)
            and m.get("role") == "assistant"
            and isinstance(m.get("content"), str)
        ]

        if len(users) == 1 and len(assistants) == 1:
            return users[0].strip(), assistants[0].strip()

        return None, None

    return (
        first_text(record, USER_KEYS),
        first_text(record, ASSISTANT_KEYS),
    )


def normalize(record, line_number):
    issues = []

    user, assistant = extract_messages(record)

    language = str(
        record.get("language") or ""
    ).strip().lower()

    tone = str(
        record.get("tone") or ""
    ).strip().lower()

    approval = str(
        record.get("review_status")
        or record.get("status")
        or ""
    ).strip().lower()

    example_id = str(
        record.get("id") or f"source-line-{line_number}"
    )

    if not user:
        issues.append("missing_user")

    if not assistant:
        issues.append("missing_assistant")

    if language not in LANGUAGES:
        issues.append("missing_or_invalid_language")

    if not tone:
        issues.append("tone_not_labeled")
    elif tone not in TONES:
        issues.append("invalid_tone")

    if approval not in APPROVAL_VALUES:
        issues.append("approval_not_verifiable")

    if user and assistant:
        if user.casefold() == assistant.casefold():
            issues.append("response_copies_user")

    standardized = {
        "id": example_id,
        "language": language or None,
        "tone": tone or None,
        "user_message": user,
        "assistant_response": assistant,
        "review_status": approval or None,
        "source": "existing_ria_reviewed_dataset",
        "source_line": line_number,
    }

    return standardized, issues


def write_json(path, value):
    with path.open("w", encoding="utf-8") as file:
        json.dump(
            value,
            file,
            ensure_ascii=False,
            indent=2,
        )


def main():
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Source dataset not found: {SOURCE_FILE}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STANDARD_DIR.mkdir(parents=True, exist_ok=True)

    records = []
    problems = []
    duplicate_keys = set()

    language_counts = Counter()
    tone_counts = Counter()
    coverage = Counter()

    with SOURCE_FILE.open(
        "r", encoding="utf-8"
    ) as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue

            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError(
                        "JSONL entry must be an object"
                    )
            except (ValueError, json.JSONDecodeError) as exc:
                problems.append({
                    "line": line_number,
                    "issues": ["invalid_json"],
                    "detail": str(exc),
                })
                continue

            record, issues = normalize(raw, line_number)

            user = record["user_message"]
            assistant = record["assistant_response"]

            if user and assistant:
                key = (
                    user.casefold(),
                    assistant.casefold(),
                )

                if key in duplicate_keys:
                    issues.append("duplicate_conversation")

                duplicate_keys.add(key)

            records.append(record)

            if record["language"] in LANGUAGES:
                language_counts[record["language"]] += 1

            if record["tone"] in TONES:
                tone_counts[record["tone"]] += 1

            if (
                record["language"] in LANGUAGES
                and record["tone"] in TONES
            ):
                coverage[
                    (
                        record["language"],
                        record["tone"],
                    )
                ] += 1

            if issues:
                problems.append({
                    "id": record["id"],
                    "line": line_number,
                    "issues": issues,
                })

    # This is an audit export, not a training split.
    standardized_path = (
        STANDARD_DIR / "ria1_audit_export.jsonl"
    )

    with standardized_path.open(
        "w", encoding="utf-8"
    ) as file:
        for record in records:
            file.write(
                json.dumps(
                    record, ensure_ascii=False
                ) + "\n"
            )

    complete_records = [
        record for record in records
        if (
            record["language"] in LANGUAGES
            and record["tone"] in TONES
            and record["review_status"] in APPROVAL_VALUES
            and record["user_message"]
            and record["assistant_response"]
        )
    ]

    report = {
        "generated_at": datetime.now().isoformat(),
        "source_file": str(SOURCE_FILE),
        "total_parsed": len(records),
        "total_issues": len(problems),
        "schema_complete_candidates": len(
            complete_records
        ),
        "language_counts": dict(language_counts),
        "tone_counts": dict(tone_counts),
        "coverage": {
            language: {
                tone: coverage[(language, tone)]
                for tone in sorted(TONES)
            }
            for language in sorted(LANGUAGES)
        },
        "issues": problems,
        "note": (
            "Candidates are not automatically cleared "
            "for model training. Human quality and "
            "provenance review are still required."
        ),
    }

    report_path = OUTPUT_DIR / "dataset_report.json"
    write_json(report_path, report)

    print("\n" + "=" * 52)
    print("RIA-1 DATASET AUDIT")
    print("=" * 52)

    print("Parsed conversations:", len(records))
    print("Records with issues:", len(problems))
    print(
        "Schema-complete candidates:",
        len(complete_records)
    )

    print("\nLANGUAGE COVERAGE")
    for language in sorted(LANGUAGES):
        print(
            f"  {language:10}: "
            f"{language_counts[language]}"
        )

    print("\nTONE COVERAGE")
    for tone in sorted(TONES):
        print(f"  {tone:20}: {tone_counts[tone]}")

    print("\nLANGUAGE x TONE MATRIX")
    for language in sorted(LANGUAGES):
        print(f"\n  {language.upper()}")
        for tone in sorted(TONES):
            print(
                f"    {tone:20}: "
                f"{coverage[(language, tone)]}"
            )

    print("\nISSUES")
    if not problems:
        print("  No structural issues found.")
    else:
        for problem in problems[:30]:
            print(
                f"  Line {problem['line']}: "
                f"{', '.join(problem['issues'])}"
            )

        if len(problems) > 30:
            print(
                f"  ...and {len(problems) - 30} more"
            )

    print("\nFILES")
    print("  Report:", report_path)
    print("  Audit export:", standardized_path)
    print("=" * 52)


if __name__ == "__main__":
    main()

