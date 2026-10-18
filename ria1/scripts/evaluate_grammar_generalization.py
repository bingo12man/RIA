
import json
from datetime import datetime, timezone
from pathlib import Path

from ria1.scripts.test_dynamic_grounding import (
    load_approved,
    build_system,
    ask_gemma,
)
from ria1.scripts.test_grammar_grounding import GRAMMAR_RULES

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ria1/data/evaluation/grammar_generalization_v1.json"

# New diagnostic examples.
# Do not add these to training or grounding references.
TESTS = [
    ("Amma inniku veetukku varala.",
     "Mom didn't come home today."),
    ("Amma inniku veetukku pogala.",
     "Mom didn't go home today."),
    ("Naan naalaikku college-ku varuven.",
     "I'll come to college tomorrow."),
    ("Naan naalaikku college-ku poven.",
     "I'll go to college tomorrow."),
    ("Avalukku indha food vendaam.",
     "She doesn't want this food."),
    ("Indha alavu saapadu podhum.",
     "This amount of food is enough."),
    ("Nethu avan call pannala.",
     "He didn't call yesterday."),
    ("Inniku enakku velai mudiyala.",
     "I couldn't finish my work today."),
    ("Naalaikku vara mudiyuma?",
     "Can you come tomorrow?"),
    ("Aval konjam kovama irukka.",
     "She's a little angry."),
    ("Enakku ippo pesa thonala.",
     "I don't feel like talking right now."),
    ("Avan vara maattennu sonnaan.",
     "He said he wouldn't come."),
]


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            "Evaluation already exists. "
            "Keep the first-run results unchanged."
        )

    records = load_approved()
    results = []

    print("\nRIA-1 FRESH GRAMMAR EVALUATION")
    print("=" * 55)

    for number, (sentence, expected) in enumerate(TESTS, 1):
        system, glossary, examples = build_system(
            sentence, records
        )

        answer = ask_gemma(
            system + "\n\n" + GRAMMAR_RULES,
            sentence,
        )

        result = {
            "id": f"RIA-GEN-{number:03d}",
            "input": sentence,
            "expected": expected,
            "actual": answer,
            "retrieved_ids": [r["id"] for r in examples],
            "review": "pending",
        }

        results.append(result)

        print(f"\nTEST {number}")
        print("INPUT:", sentence)
        print("EXPECTED:", expected)
        print("RIA:", answer)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        json.dumps(
            {
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "model": "gemma3:4b",
                "evaluation_type": "first-run developmental",
                "grammar_rules_frozen_for_run": True,
                "tests": results,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("\nSaved:", OUTPUT)
    print("Human meaning review required.")


if __name__ == "__main__":
    main()

