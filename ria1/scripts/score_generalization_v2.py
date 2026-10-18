
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "ria1/data/evaluation/generalization_v2_frozen"

PROMPTS = FOLDER / "prompts.jsonl"
ANSWERS = FOLDER / "answer_key.jsonl"
PREDICTIONS = FOLDER / "model_predictions_v1.jsonl"
MANIFEST = FOLDER / "manifest.json"

REVIEWS = FOLDER / "human_scores_v1.json"
REPORT = FOLDER / "scoring_report_v1.json"

METHODS = [
    "direct",
    "indicxlit_top1",
    "verified_converter",
]


def load_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, data):
    temp = path.with_suffix(".tmp")

    temp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    temp.replace(path)


def get_score():
    while True:
        value = input(
            "Score [2 correct / 1 partial / 0 wrong / q quit]: "
        ).strip().lower()

        if value == "q":
            return None

        if value in ("0", "1", "2"):
            return int(value)

        print("Please enter 0, 1, 2 or q.")


def get_critical():
    while True:
        value = input(
            "Critical meaning error? [y/N]: "
        ).strip().lower()

        if value in ("", "n", "no"):
            return False

        if value in ("y", "yes"):
            return True

        print("Enter y or n.")


def calculate_report(prompts, reviews):
    categories = {
        row["id"]: row["category"]
        for row in prompts
    }

    overall = {}
    by_category = {}

    for method in METHODS:
        scores = []
        critical = 0

        groups = defaultdict(list)

        for rid, method_reviews in reviews.items():
            entry = method_reviews.get(method)

            if not entry:
                continue

            score = entry["score"]
            scores.append(score)

            if entry["critical"]:
                critical += 1

            category = categories[rid]
            groups[category].append(score)

        count = len(scores)

        overall[method] = {
            "reviewed": count,
            "correct": scores.count(2),
            "partial": scores.count(1),
            "incorrect": scores.count(0),
            "critical_errors": critical,
            "mean_score": (
                round(sum(scores) / count, 3)
                if count else None
            ),
            "fully_correct_percent": (
                round(100 * scores.count(2) / count, 1)
                if count else None
            ),
        }

        by_category[method] = {
            category: {
                "reviewed": len(values),
                "fully_correct": values.count(2),
                "mean_score": round(
                    sum(values) / len(values), 3
                ),
            }
            for category, values in sorted(groups.items())
        }

    return {
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "evaluation": "generalization_v2",
        "total_prompts": len(prompts),
        "overall": overall,
        "by_category": by_category,
        "limitations": [
            "Human-scored developmental evaluation.",
            "Reviewers are not blinded to method names.",
            "A perfect score does not establish production safety.",
            "Current-turn conversion only; earlier context was not converted.",
        ],
    }


def main():
    manifest = json.loads(
        MANIFEST.read_text(encoding="utf-8")
    )

    if sha256(PROMPTS) != manifest["prompts_sha256"]:
        raise ValueError("Frozen prompts changed")

    if sha256(ANSWERS) != manifest["answer_key_sha256"]:
        raise ValueError("Frozen answers changed")

    prompts = load_jsonl(PROMPTS)
    answers = load_jsonl(ANSWERS)
    predictions = load_jsonl(PREDICTIONS)

    if not (
        len(prompts) == len(answers) ==
        len(predictions) == 40
    ):
        raise ValueError("Expected 40 records per file")

    prompts_by_id = {r["id"]: r for r in prompts}
    answers_by_id = {r["id"]: r for r in answers}
    predictions_by_id = {r["id"]: r for r in predictions}

    ids = set(prompts_by_id)

    if (
        len(ids) != 40
        or len(answers_by_id) != 40
        or len(predictions_by_id) != 40
        or ids != set(answers_by_id)
        or ids != set(predictions_by_id)
    ):
        raise ValueError("Duplicate or mismatched IDs")

    if REVIEWS.exists():
        state = json.loads(
            REVIEWS.read_text(encoding="utf-8")
        )

        if state["predictions_sha256"] != sha256(PREDICTIONS):
            raise ValueError(
                "Predictions changed since review began"
            )

        reviews = state["reviews"]
    else:
        reviews = {}

    total = len(prompts) * len(METHODS)

    print("\nRIA-1 HUMAN SCORING — MODULE 4.49")
    print("=" * 60)
    print("Total predictions:", total)
    print("Previously reviewed:", sum(
        len(v) for v in reviews.values()
    ))
    print("Enter q to save and exit.\n")

    for index, prompt in enumerate(prompts, 1):
        rid = prompt["id"]
        answer = answers_by_id[rid]
        predicted = predictions_by_id[rid]["predictions"]

        reviews.setdefault(rid, {})

        if all(
            method in reviews[rid]
            for method in METHODS
        ):
            continue

        print("\n" + "=" * 65)
        print(f"{index}/40 — {rid}")
        print("CATEGORY:", prompt["category"])

        if prompt.get("previous_user"):
            print("PREVIOUS USER:", prompt["previous_user"])
            print("PREVIOUS RIA:", prompt["previous_ria"])

        print("CURRENT USER:", prompt["user_message"])
        print("EXPECTED:", answer["expected_english"])

        for method in METHODS:
            if method in reviews[rid]:
                continue

            print("\nMETHOD:", method.upper())
            print("PREDICTION:", predicted[method])

            score = get_score()

            if score is None:
                save_json(REVIEWS, {
                    "predictions_sha256": sha256(PREDICTIONS),
                    "reviews": reviews,
                })

                print("\nProgress saved.")
                return

            critical = get_critical() if score < 2 else False

            notes = input(
                "Optional error note [Enter to skip]: "
            ).strip()

            reviews[rid][method] = {
                "score": score,
                "critical": critical,
                "notes": notes,
                "reviewed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

            save_json(REVIEWS, {
                "predictions_sha256": sha256(PREDICTIONS),
                "reviews": reviews,
            })

            print("Saved.")

    report = calculate_report(prompts, reviews)
    save_json(REPORT, report)

    print("\n" + "=" * 60)
    print("RIA-1 SCORING COMPLETE")
    print("=" * 60)

    for method, result in report["overall"].items():
        print(f"\n{method.upper()}")
        print("Correct:", result["correct"])
        print("Partial:", result["partial"])
        print("Incorrect:", result["incorrect"])
        print("Critical errors:", result["critical_errors"])
        print("Mean score:", result["mean_score"])

    print("\nReport:", REPORT)


if __name__ == "__main__":
    main()

