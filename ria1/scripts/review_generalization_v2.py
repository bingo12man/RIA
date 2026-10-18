
import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "ria1/data/evaluation"
CANDIDATE = EVAL / "generalization_v2"
FROZEN = EVAL / "generalization_v2_frozen"

PROMPTS = CANDIDATE / "prompts.jsonl"
ANSWERS = CANDIDATE / "answer_key.jsonl"

TRAINING = (
    ROOT / "ria1/data/releases/language_foundation_v1/"
    "meaning_reference.jsonl"
)
BENCHMARK = EVAL / "tanglish_comprehension_v1.jsonl"

HISTORY = CANDIDATE / "human_reviews.json"


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path, rows):
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text):
    return " ".join(
        re.findall(r"\w+", text.casefold())
    )


def previous_examples():
    examples = []

    for row in read_jsonl(TRAINING):
        examples.append(("training", row["tanglish"]))

    for row in read_jsonl(BENCHMARK):
        examples.append(("benchmark", row["user_message"]))

    previous_json = [
        "grammar_generalization_v1.json",
        "tamil_script_diagnostic_v1.json",
        "gemma_transliteration_v1.json",
        "indicxlit_unseen_pipeline_v1.json",
        "direct_vs_converted_comparison_v1.json",
    ]

    for filename in previous_json:
        path = EVAL / filename

        if not path.exists():
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        records = (
            data if isinstance(data, list)
            else data.get("tests", [])
        )

        for row in records:
            sentence = (
                row.get("tanglish")
                or row.get("original")
                or row.get("input")
            )
            if sentence:
                examples.append((filename, sentence))

    return examples


def check_overlap(prompts):
    references = previous_examples()
    warnings = []

    for row in prompts:
        for source, text in references:
            score = SequenceMatcher(
                None,
                normalize(row["user_message"]),
                normalize(text),
            ).ratio()

            if score >= 0.78:
                warnings.append({
                    "id": row["id"],
                    "source": source,
                    "similarity": round(score, 3),
                    "candidate": row["user_message"],
                    "previous": text,
                })

    # Also screen against other questions in this set.
    for i, a in enumerate(prompts):
        for b in prompts[i + 1:]:
            score = SequenceMatcher(
                None,
                normalize(a["user_message"]),
                normalize(b["user_message"]),
            ).ratio()

            if score >= 0.85:
                warnings.append({
                    "id": a["id"],
                    "other_id": b["id"],
                    "source": "within_candidate_set",
                    "similarity": round(score, 3),
                })

    return warnings


def main():
    prompts = read_jsonl(PROMPTS)
    answers = read_jsonl(ANSWERS)

    assert len(prompts) == len(answers) == 40

    prompt_map = {r["id"]: r for r in prompts}
    answer_map = {r["id"]: r for r in answers}

    assert len(prompt_map) == len(answer_map) == 40
    assert set(prompt_map) == set(answer_map)

    print("\nRIA-1 GENERALIZATION V2 QUALITY GATE")
    print("=" * 58)

    warnings = check_overlap(prompts)
    print("Overlap warnings:", len(warnings))

    for warning in warnings[:20]:
        print(json.dumps(warning, ensure_ascii=False))

    if warnings:
        print("\nFREEZE BLOCKED: resolve overlaps first.")
        return

    reviews = {}

    if HISTORY.exists():
        reviews = json.loads(
            HISTORY.read_text(encoding="utf-8")
        )

    print("\nHUMAN MEANING REVIEW")
    print("Enter y to approve, e to edit meaning, q to quit.")

    for index, prompt in enumerate(prompts, 1):
        rid = prompt["id"]
        answer = answer_map[rid]

        previous = reviews.get(rid, {})

        if (
            previous.get("status") == "approved"
            and previous.get("prompt") == prompt
        ):
            continue

        print("\n" + "=" * 58)
        print(f"{index}/40 — {rid}")
        print("CATEGORY:", prompt["category"])

        if prompt.get("previous_user"):
            print("PREVIOUS USER:", prompt["previous_user"])
            print("PREVIOUS RIA:", prompt["previous_ria"])

        print("CURRENT USER:", prompt["user_message"])
        print("ENGLISH MEANING:", answer["expected_english"])

        choice = input("Approve [y/e/q]: ").strip().lower()

        if choice == "q":
            break

        if choice == "e":
            edited = input("Correct English meaning: ").strip()

            if not edited:
                print("Empty correction; skipped.")
                continue

            answer["expected_english"] = edited
            choice = "y"

        if choice != "y":
            print("Not approved.")
            continue

        reviews[rid] = {
            "status": "approved",
            "prompt": prompt,
            "expected_english": answer["expected_english"],
            "reviewed_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        HISTORY.write_text(
            json.dumps(
                reviews,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        print("Approved.")

    approved = sum(
        1 for row in prompts
        if (
            reviews.get(row["id"], {}).get("status")
            == "approved"
            and reviews[row["id"]].get("prompt") == row
        )
    )

    print("\nApproved:", approved, "/ 40")

    if approved != 40:
        print("Freeze pending. Run again to resume.")
        return

    if FROZEN.exists():
        raise FileExistsError(
            "Frozen set already exists: " + str(FROZEN)
        )

    FROZEN.mkdir(parents=True, exist_ok=False)

    frozen_prompts = FROZEN / "prompts.jsonl"
    frozen_answers = FROZEN / "answer_key.jsonl"

    final_answers = [
        {
            "id": row["id"],
            "expected_english": reviews[row["id"]]["expected_english"],
            "human_review": "approved",
        }
        for row in prompts
    ]

    write_jsonl(frozen_prompts, prompts)
    write_jsonl(frozen_answers, final_answers)

    manifest = {
        "release": "generalization_v2_frozen",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "count": 40,
        "single_turn": 32,
        "context": 8,
        "overlap_warnings": 0,
        "human_approved": 40,
        "prompts_sha256": sha256(frozen_prompts),
        "answer_key_sha256": sha256(frozen_answers),
        "status": "frozen_development_evaluation",
        "limitations": [
            "Author-created examples require independent language review.",
            "Lexical screening does not rule out semantic overlap.",
            "This is a development holdout, not an independent production benchmark.",
            "No evaluation content should enter training or retrieval.",
        ],
    }

    (FROZEN / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print("\nRIA-1 EVALUATION SET FROZEN")
    print("=" * 58)
    print("Approved:", approved)
    print("Frozen examples:", len(prompts))
    print("Output:", FROZEN)
    print("Status: Ready for development evaluation")


if __name__ == "__main__":
    main()

