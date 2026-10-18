
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]

NODE_RESULTS = (
    ROOT / "ria1/experiments/indicxlit_node/"
    "indicxlit_node_results.json"
)

REFERENCE = (
    ROOT / "ria1/data/evaluation/"
    "tamil_script_diagnostic_v1.json"
)

OUTPUT = (
    ROOT / "ria1/data/evaluation/"
    "indicxlit_gemma_pipeline_v1.json"
)

URL = "http://127.0.0.1:11434/api/chat"

SYSTEM = """
You understand conversational Tamil, including
English technical words mixed into Tamil sentences.

Translate the user's intended meaning into one
natural English sentence.

Preserve:
- Subject and pronouns
- Past, present and future tense
- Negation
- Come versus go
- Emotional meaning
- Questions and reported speech

Do not add facts.
Do not answer the user's request.
Return only the English translation.
"""


def ask_gemma(sentence):
    payload = {
        "model": "gemma3:4b",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM.strip(),
            },
            {
                "role": "user",
                "content": sentence,
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 120,
        },
    }

    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=120
    ) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            "This experiment already exists. "
            "Do not overwrite the first results."
        )

    conversions = json.loads(
        NODE_RESULTS.read_text(encoding="utf-8")
    )

    reference_data = json.loads(
        REFERENCE.read_text(encoding="utf-8")
    )

    references = {
        row["tanglish"]: row
        for row in reference_data["tests"]
    }

    results = []

    print("\nRIA-1 INDICXLIT + GEMMA PIPELINE")
    print("=" * 60)

    for number, record in enumerate(
        conversions, 1
    ):
        original = record["original"]
        converted = record["converted"]

        reference = references.get(original)

        if reference is None:
            raise ValueError(
                f"Missing evaluation reference: {original}"
            )

        predicted = ask_gemma(converted)

        result = {
            "id": f"RIA-IX-{number:03d}",
            "tanglish": original,
            "indicxlit_tamil": converted,
            "reference_tamil": reference["tamil"],
            "expected_english": reference["expected"],
            "predicted_english": predicted,
            "human_review": "pending",
        }

        results.append(result)

        print(f"\nTEST {number}")
        print("ORIGINAL:", original)
        print("INDICXLIT:", converted)
        print("EXPECTED:", reference["expected"])
        print("PREDICTED:", predicted)

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            {
                "model": "gemma3:4b",
                "converter": "indicxlit_node_top1",
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "evaluation_type": "development_diagnostic",
                "tests": results,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("\nSaved:", OUTPUT)
    print("Human meaning evaluation required.")


if __name__ == "__main__":
    main()

