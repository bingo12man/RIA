
import json
from pathlib import Path

from ria1.scripts.test_dynamic_grounding import (
    load_approved,
    build_system,
    ask_gemma,
)

ROOT = Path(__file__).resolve().parents[2]

GRAMMAR_RULES = """
GRAMMAR AND MEANING RULES:

1. Preserve who is doing the action.
   naan = I; avan = he; aval = she.

2. Preserve direction:
   vara = come / attend, depending on context.
   poga = go.
   varala = did not come.
   pogala = did not go.

3. Preserve time:
   netru = yesterday.
   inniku = today.
   naalaikku = tomorrow.

4. Preserve possibility and negation:
   mudiyadhu = cannot / not possible.
   vara mudiyadhu = cannot come or attend.
   vendaam = do not want.
   podhum = enough or sufficient.

5. Natural English:
   enakku sometimes marks the experiencer.
   Translate "enakku bayama irukku" as
   "I'm scared", not "I'm scared for me".

6. Preserve speaker perspective.
   "I cannot attend tomorrow's meeting" is
   not the same as "Tomorrow's meeting is impossible".

7. Preserve tense and factual meaning.
   Do not turn past absence into future inability.

8. Return one natural English sentence only.
   Do not explain the translation process.
"""

TESTS = [
    {
        "input": "Enakku coffee vendaam, tea podhum.",
        "expected": "I don't want coffee; tea is enough.",
    },
    {
        "input": "Enakku tea vendaam, coffee podhum.",
        "expected": "I don't want tea; coffee is enough.",
    },
    {
        "input": "Naan inniku office-ku pogala.",
        "expected": "I didn't go to the office today.",
    },
    {
        "input": "Enakku konjam bayama irukku.",
        "expected": "I'm feeling a little scared.",
    },
    {
        "input": "Avan netru school-ku varala.",
        "expected": "He didn't come to school yesterday.",
    },
    {
        "input": "Naalaikku meeting-ku vara mudiyadhu.",
        "expected": "I won't be able to attend tomorrow's meeting.",
    },
]

def main():
    records = load_approved()
    results = []

    print("\nRIA-1 GRAMMAR-AWARE GROUNDING")
    print("=" * 55)

    for i, test in enumerate(TESTS, 1):
        query = test["input"]

        system, glossary, examples = build_system(
            query, records
        )

        revised_system = (
            system + "\n\n" + GRAMMAR_RULES
        )

        answer = ask_gemma(revised_system, query)

        print(f"\nTEST {i}")
        print("INPUT:", query)
        print("EXPECTED:", test["expected"])
        print("RIA:", answer)
        print("RETRIEVED:", [r["id"] for r in examples])

        results.append({
            "input": query,
            "expected": test["expected"],
            "response": answer,
            "retrieved_ids": [r["id"] for r in examples],
        })

    output = (
        ROOT / "ria1/data/evaluation/"
        "grammar_grounding_diagnostic.json"
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            results,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nSaved:", output)
    print("Human evaluation required.")


if __name__ == "__main__":
    main()

