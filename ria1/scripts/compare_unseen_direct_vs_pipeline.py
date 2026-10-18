
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "ria1/data/evaluation"

SOURCE = EVAL / "indicxlit_unseen_pipeline_v1.json"
OUTPUT = EVAL / "direct_vs_converted_comparison_v1.json"

SYSTEM = (
    "You understand conversational Tamil and Tanglish. "
    "Explain the user's meaning in one natural English "
    "sentence. Preserve subjects, tense, negation, "
    "questions, actions and emotions. Do not add facts. "
    "Do not answer the user's request. "
    "Return only the English meaning."
)


def ask_gemma(sentence):
    payload = {
        "model": "gemma3:4b",
        "messages": [
            {"role": "system", "content": SYSTEM},
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

    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["message"]["content"].strip()


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Comparison already exists: {OUTPUT}"
        )

    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    results = []

    print("\nRIA-1 DIRECT VS CONVERTED COMPARISON")
    print("=" * 60)

    for i, row in enumerate(source["tests"], 1):
        original = row["original"]
        converted = row["converted_tamil"]

        # Identical prompt and generation settings
        # for both methods.
        direct = ask_gemma(original)
        converted_answer = ask_gemma(converted)

        result = {
            "id": row["id"],
            "input": original,
            "converted_tamil": converted,
            "expected": row["expected_english"],
            "direct": direct,
            "converted": converted_answer,
            "direct_human_score": None,
            "converted_human_score": None,
            "benchmark_overlap": i == 8,
        }

        results.append(result)

        print(f"\nTEST {i}")
        print("INPUT:", original)
        print("EXPECTED:", row["expected_english"])
        print("DIRECT:", direct)
        print("CONVERTED:", converted_answer)

    OUTPUT.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "model": "gemma3:4b",
                "evaluation": "paired_development_comparison",
                "tests": results,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("\nSaved:", OUTPUT)
    print("Manual scoring required.")


if __name__ == "__main__":
    main()

