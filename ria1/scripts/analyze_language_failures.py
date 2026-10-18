
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ria1/data/evaluation/generalization_v2_frozen"

METHODS = [
    "direct",
    "indicxlit_top1",
    "verified_converter",
]


def load_jsonl(name):
    path = DATA / name
    return {
        record["id"]: record
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for record in [json.loads(line)]
    }


def main():
    prompts = load_jsonl("prompts.jsonl")
    answers = load_jsonl("answer_key.jsonl")
    predictions = load_jsonl("model_predictions_v1.jsonl")

    human = json.loads(
        (DATA / "human_scores_v1.json").read_text(
            encoding="utf-8"
        )
    )["reviews"]

    assert len(prompts) == len(answers) == len(predictions) == 40
    assert set(prompts) == set(answers) == set(predictions)
    assert all(
        all(method in human.get(rid, {}) for method in METHODS)
        for rid in prompts
    ), "Human scoring is incomplete."

    by_category = defaultdict(
        lambda: defaultdict(
            lambda: {"correct": 0, "partial": 0, "wrong": 0, "critical": 0}
        )
    )

    critical_cases = []
    verified_wins = []
    verified_losses = []
    equal_cases = []

    for rid, prompt in prompts.items():
        category = prompt["category"]

        for method in METHODS:
            review = human[rid][method]
            score = review["score"]
            stats = by_category[category][method]

            if score == 2:
                stats["correct"] += 1
            elif score == 1:
                stats["partial"] += 1
            else:
                stats["wrong"] += 1

            if review["critical"]:
                stats["critical"] += 1

        top = human[rid]["indicxlit_top1"]["score"]
        verified = human[rid]["verified_converter"]["score"]

        if verified > top:
            verified_wins.append(rid)
        elif verified < top:
            verified_losses.append(rid)
        else:
            equal_cases.append(rid)

        if any(
            human[rid][method]["critical"]
            for method in METHODS
        ):
            critical_cases.append(rid)

    print("\nRIA-1 — MODULE 4.50")
    print("LANGUAGE FAILURE ANALYSIS")
    print("=" * 65)

    print("\nPERFORMANCE BY CATEGORY")
    for category in sorted(by_category):
        print(f"\n{category.upper()}")

        for method in METHODS:
            stats = by_category[category][method]
            print(
                f"  {method:20s} "
                f"correct={stats['correct']} "
                f"partial={stats['partial']} "
                f"wrong={stats['wrong']} "
                f"critical={stats['critical']}"
            )

    print("\nVERIFIED VS TOP-1")
    print("Verified better:", len(verified_wins), verified_wins)
    print("Verified worse:", len(verified_losses), verified_losses)
    print("Same score:", len(equal_cases))

    print("\nCRITICAL ERROR CASES")
    print("=" * 65)

    for rid in critical_cases:
        print(f"\n{rid} — {prompts[rid]['category']}")
        print("INPUT:", prompts[rid]["user_message"])
        print("EXPECTED:", answers[rid]["expected_english"])

        for method in METHODS:
            review = human[rid][method]

            if review["critical"]:
                print(
                    f"\n  {method} "
                    f"[score={review['score']}]"
                )
                print(
                    "  PREDICTION:",
                    predictions[rid]["predictions"][method]
                )
                print(
                    "  NOTES:",
                    review.get("notes", "")
                )

    report = {
        "category_breakdown": {
            category: dict(methods)
            for category, methods in by_category.items()
        },
        "verified_better_ids": verified_wins,
        "verified_worse_ids": verified_losses,
        "equal_score_ids": equal_cases,
        "critical_case_ids": critical_cases,
        "total_cases": 40,
    }

    output = DATA / "failure_analysis_v1.json"

    if output.exists():
        raise FileExistsError(
            f"Report already exists: {output}"
        )

    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print("\nSaved:", output)


if __name__ == "__main__":
    main()

