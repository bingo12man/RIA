
import json
from pathlib import Path

from ria1.scripts.test_dynamic_grounding import ask_gemma

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "ria1/data/evaluation"

CONVERSIONS = EVAL / "gemma_transliteration_v1.json"
REFERENCE = EVAL / "tamil_script_diagnostic_v1.json"
OUTPUT = EVAL / "automatic_conversion_pipeline_v1.json"

SYSTEM = """
You understand conversational Tamil written in Tamil script.

Translate the following sentence into natural English.
Preserve the subject, action, tense, negation and intent.
Do not invent details. Do not answer the user's request.
Return only one English sentence.
"""


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            "Results already exist. Do not overwrite."
        )

    conversions = json.loads(
        CONVERSIONS.read_text(encoding="utf-8")
    )

    reference_data = json.loads(
        REFERENCE.read_text(encoding="utf-8")
    )

    references = {
        row["tanglish"]: row
        for row in reference_data["tests"]
    }

    results = []

    print("\nRIA-1 AUTOMATIC CONVERSION PIPELINE")
    print("=" * 55)

    for index, row in enumerate(conversions, 1):
        original = row["input"]
        converted = row["converted"]

        reference = references.get(original)

        if reference is None:
            raise ValueError(
                f"Missing reference for: {original}"
            )

        predicted = ask_gemma(SYSTEM, converted)

        result = {
            "id": row["id"],
            "tanglish": original,
            "converted_tamil": converted,
            "reference_tamil": reference["tamil"],
            "expected_english": reference["expected"],
            "predicted_english": predicted,
            "human_score": None,
        }

        results.append(result)

        print(f"\nTEST {index}")
        print("ORIGINAL:", original)
        print("CONVERTED:", converted)
        print("EXPECTED:", reference["expected"])
        print("PREDICTED:", predicted)

    OUTPUT.write_text(
        json.dumps(
            {
                "model": "gemma3:4b",
                "experiment": "automatic_two_stage_pipeline",
                "tests": results,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("\nSaved:", OUTPUT)
    print("Human evaluation required.")


if __name__ == "__main__":
    main()

