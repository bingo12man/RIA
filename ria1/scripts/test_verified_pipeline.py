
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "ria1/data/evaluation"

VERIFIED = (
    ROOT / "ria1/experiments/indicxlit_node/"
    "indicxlit_verified_v1.json"
)
REFERENCE = EVAL / "tamil_script_diagnostic_v1.json"
OUTPUT = EVAL / "verified_indicxlit_gemma_v1.json"

SYSTEM = """
You understand conversational Tamil written in Tamil
script, sometimes mixed with English words.

Translate the sentence into one natural English sentence.

Preserve the subject, pronouns, tense, negation,
verb direction, questions and emotional meaning.

Do not add people, objects or events.
Do not answer the user's request.
Return only the English meaning.
"""


def ask_gemma(sentence):
    payload = {
        "model": "gemma3:4b",
        "messages": [
            {"role": "system", "content": SYSTEM.strip()},
            {"role": "user", "content": sentence},
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 120,
        },
    }

    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=120
    ) as response:
        data = json.load(response)

    return data["message"]["content"].strip()


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            "First-run results already exist: " + str(OUTPUT)
        )

    verified_data = json.loads(
        VERIFIED.read_text(encoding="utf-8")
    )["results"]

    reference_data = json.loads(
        REFERENCE.read_text(encoding="utf-8")
    )["tests"]

    references = {
        row["tanglish"]: row
        for row in reference_data
    }

    results = []

    print("\nRIA-1 VERIFIED INDICXLIT + GEMMA")
    print("=" * 60)

    for i, row in enumerate(verified_data, 1):
        original = row["original"]
        converted = row["verified_tamil"]

        if original not in references:
            raise ValueError(
                f"Reference missing: {original}"
            )

        expected = references[original]["expected"]
        prediction = ask_gemma(converted)

        print(f"\nTEST {i}")
        print("ORIGINAL:", original)
        print("TAMIL:", converted)
        print("EXPECTED:", expected)
        print("RIA:", prediction)

        results.append({
            "id": f"RIA-VER-{i:03d}",
            "original": original,
            "tamil": converted,
            "expected": expected,
            "predicted": prediction,
            "human_review": "pending",
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        json.dumps(
            {
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "converter": "indicxlit_with_verified_lexicon",
                "model": "gemma3:4b",
                "evaluation_type": "development_regression",
                "tests": results,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("\nSaved:", OUTPUT)
    print("Human scoring required.")


if __name__ == "__main__":
    main()

