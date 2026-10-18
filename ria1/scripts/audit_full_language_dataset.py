
import difflib
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "ria1/data/language_foundation"
APPROVED = DATA / "approved"

CHATS = APPROVED / "language_all_chat.jsonl"
MEANINGS = APPROVED / "language_all_meanings.jsonl"
EXPORT_REPORT = APPROVED / "language_all_report.json"

BENCHMARK = (
    ROOT / "ria1/data/evaluation/"
    "tanglish_comprehension_v1.jsonl"
)

PILOT = (
    ROOT / "ria1/data/standardized/"
    "ria1_v2_deduplicated.jsonl"
)

AUDIT = ROOT / "ria1/data/audit"
REPORT_PATH = AUDIT / "language_foundation_full_audit.json"

BATCHES = [
    "pronouns_verbs_001",
    "everyday_vocabulary_001",
    "negation_corrections_001",
    "emotion_intent_001",
    "context_switching_001",
]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for number, line in enumerate(file, 1):
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(
                        f"{path.name}:{number} is not an object"
                    )
                rows.append(row)
    return rows


def normalize(text):
    return " ".join(
        re.sub(r"[^\w\s]", " ", text.casefold()).split()
    )


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def similarity(a, b):
    return difflib.SequenceMatcher(
        None, normalize(a), normalize(b)
    ).ratio()


def main():
    errors = []
    warnings = []

    chats = load_jsonl(CHATS)
    meanings = load_jsonl(MEANINGS)
    benchmark = load_jsonl(BENCHMARK)
    export_report = load_json(EXPORT_REPORT)

    chat_map = {
        str(r["id"]): r for r in chats
    }
    meaning_map = {
        str(r["id"]): r for r in meanings
    }

    if len(chat_map) != len(chats):
        errors.append("Duplicate chat IDs")

    if len(meaning_map) != len(meanings):
        errors.append("Duplicate meaning IDs")

    if set(chat_map) != set(meaning_map):
        errors.append(
            "Chat and meaning exports have different IDs"
        )

    if len(chats) != export_report["exported"]:
        errors.append(
            "Chat count differs from unified export report"
        )

    if len(meanings) != export_report["exported"]:
        errors.append(
            "Meaning count differs from unified export report"
        )

    approved_source_ids = set()
    source_map = {}
    source_counts = Counter()
    source_hashes = {}

    for batch in BATCHES:
        source_path = DATA / f"{batch}.jsonl"
        review_path = DATA / f"{batch}_reviews.json"

        source = load_jsonl(source_path)
        reviews = load_json(review_path)["reviews_by_id"]

        ids = [str(r["id"]) for r in source]

        if len(ids) != len(set(ids)):
            errors.append(f"Duplicate source IDs: {batch}")

        if set(ids) != set(reviews):
            errors.append(
                f"Unreviewed or unknown IDs in {batch}"
            )

        source_hashes[batch] = {
            "source_sha256": sha256(source_path),
            "review_sha256": sha256(review_path),
        }

        for row in source:
            rid = str(row["id"])

            if rid in source_map:
                errors.append(f"Duplicate global ID: {rid}")

            source_map[rid] = row

            review = reviews.get(rid, {})

            if review.get("status") == "approved":
                approved_source_ids.add(rid)
                source_counts[batch] += 1

                for field in (
                    "english_meaning",
                    "tamil_equivalent",
                    "ria_response",
                ):
                    value = review.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(
                            f"{rid}: approved review missing {field}"
                        )

    blocked_ids = {
        str(row["id"])
        for row in export_report.get(
            "blocked_for_overlap_review", []
        )
    }

    expected_ids = approved_source_ids - blocked_ids

    if set(chat_map) != expected_ids:
        errors.append(
            "Exported IDs do not equal approved IDs minus "
            "blocked IDs"
        )

    if not blocked_ids.issubset(approved_source_ids):
        errors.append("Blocked IDs are not approved source IDs")

    if len(approved_source_ids) != export_report["approved"]:
        errors.append(
            "Approved source count differs from export report"
        )

    context_count = 0
    script_warnings = []
    categories = Counter()

    for rid in sorted(set(chat_map) & set(meaning_map)):
        chat = chat_map[rid]
        meaning = meaning_map[rid]
        source = source_map.get(rid)

        if source is None:
            errors.append(f"{rid}: missing source record")
            continue

        categories[source["category"]] += 1

        messages = chat.get("messages")

        if not isinstance(messages, list):
            errors.append(
                f"{rid}: missing messages array; "
                "exporter must preserve conversation turns"
            )
            continue

        expected_roles = (
            ["user", "assistant", "user", "assistant"]
            if source.get("previous_user")
            else ["user", "assistant"]
        )

        actual_roles = [
            message.get("role") for message in messages
        ]

        if actual_roles != expected_roles:
            errors.append(
                f"{rid}: expected roles {expected_roles}, "
                f"got {actual_roles}"
            )
            continue

        for message in messages:
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                errors.append(f"{rid}: empty message")

        if source.get("previous_user"):
            context_count += 1

            if (
                messages[0]["content"]
                != source["previous_user"]
                or messages[1]["content"]
                != source["previous_ria"]
            ):
                errors.append(
                    f"{rid}: previous conversation changed"
                )

        if (
            messages[-2]["content"]
            != source["user_message"].strip()
        ):
            errors.append(f"{rid}: user message changed")

        meaning_user = meaning.get("tanglish")

        if normalize(str(meaning_user or "")) != normalize(
            source["user_message"]
        ):
            errors.append(f"{rid}: meaning input mismatch")

        english = meaning.get("english_meaning")
        tamil = meaning.get("tamil_equivalent")

        if not isinstance(english, str) or not english.strip():
            errors.append(f"{rid}: missing English meaning")

        if not isinstance(tamil, str) or not tamil.strip():
            errors.append(f"{rid}: missing Tamil equivalent")

        elif not re.search(r"[\u0B80-\u0BFF]", tamil):
            script_warnings.append({
                "id": rid,
                "issue": "Tamil equivalent lacks Tamil script",
            })

        if (
            chat.get("language") != "tanglish"
        ):
            errors.append(f"{rid}: incorrect language")

        answer = messages[-1]["content"]

        if re.search(r"[\u0B80-\u0BFF]", answer):
            script_warnings.append({
                "id": rid,
                "issue": "Tanglish answer contains Tamil script",
            })

    # Detect exact duplicates and high text similarity
    # within the training candidate export.
    within_dataset = []

    ids = list(chat_map)

    for i, first_id in enumerate(ids):
        for second_id in ids[i + 1:]:
            first = chat_map[first_id]
            second = chat_map[second_id]

            first_msg = first.get("messages", [])
            second_msg = second.get("messages", [])

            if not first_msg or not second_msg:
                continue

            a = first_msg[-2]["content"]
            b = second_msg[-2]["content"]

            score = similarity(a, b)

            if score >= 0.82:
                within_dataset.append({
                    "first_id": first_id,
                    "second_id": second_id,
                    "similarity": round(score, 3),
                    "first_prompt": a,
                    "second_prompt": b,
                })

    # Check similarity to held-out benchmark.
    benchmark_warnings = []

    for rid, chat in chat_map.items():
        messages = chat.get("messages", [])

        if not messages:
            continue

        user_turns = [
            m["content"] for m in messages
            if m.get("role") == "user"
        ]

        for user_text in user_turns:
            for test in benchmark:
                score = similarity(
                    user_text, test["user_message"]
                )

                if score >= 0.78:
                    benchmark_warnings.append({
                        "training_id": rid,
                        "benchmark_id": test["id"],
                        "similarity": round(score, 3),
                        "training_prompt": user_text,
                        "benchmark_prompt": test["user_message"],
                    })

    # The earlier conversational pilot may contain
    # similar wording to language-foundation examples.
    pilot_warnings = []

    if PILOT.exists():
        pilot_rows = load_jsonl(PILOT)

        for rid, chat in chat_map.items():
            messages = chat.get("messages", [])

            if not messages:
                continue

            user = messages[-2]["content"]

            for existing in pilot_rows:
                other = existing.get("user_message", "")

                score = similarity(user, other)

                if score >= 0.82:
                    pilot_warnings.append({
                        "language_id": rid,
                        "pilot_id": existing.get("id"),
                        "similarity": round(score, 3),
                    })

    report = {
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "approved_source_records": len(approved_source_ids),
        "blocked_source_records": len(blocked_ids),
        "exported_chat_records": len(chats),
        "exported_meaning_records": len(meanings),
        "multi_turn_records": context_count,
        "source_counts": dict(source_counts),
        "exported_categories": dict(categories),
        "errors": errors,
        "script_warnings": script_warnings,
        "internal_duplicate_warnings": within_dataset,
        "benchmark_overlap_warnings": benchmark_warnings,
        "pilot_overlap_warnings": pilot_warnings,
        "source_hashes": source_hashes,
        "chat_sha256": sha256(CHATS),
        "meaning_sha256": sha256(MEANINGS),
        "benchmark_sha256": sha256(BENCHMARK),
        "training_ready": False,
        "notes": [
            "Structural checks do not establish semantic correctness.",
            "Similarity warnings require manual review.",
            "The 30-case benchmark must remain held out.",
            "Training readiness requires a separate release decision.",
        ],
    }

    AUDIT.mkdir(parents=True, exist_ok=True)

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nRIA-1 FULL LANGUAGE DATASET AUDIT")
    print("=" * 55)
    print("Approved source:", len(approved_source_ids))
    print("Exported chats:", len(chats))
    print("Exported meanings:", len(meanings))
    print("Multi-turn records:", context_count)
    print("Structural errors:", len(errors))
    print("Script warnings:", len(script_warnings))
    print("Internal duplicate warnings:", len(within_dataset))
    print("Benchmark overlap warnings:", len(benchmark_warnings))
    print("Pilot overlap warnings:", len(pilot_warnings))
    print("Report:", REPORT_PATH)

    if errors:
        print("\nFIRST STRUCTURAL ERRORS")
        for item in errors[:10]:
            print(" -", item)

    print("\nSTATUS")
    print(
        "Structural audit passed"
        if not errors
        else "Structural audit needs fixes"
    )
    print("Training ready: No — review still required")


if __name__ == "__main__":
    main()

