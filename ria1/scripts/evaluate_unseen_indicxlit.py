
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT / "ria1/experiments/indicxlit_node/"
    "indicxlit_unseen_v1.json"
)
OUTPUT = (
    ROOT / "ria1/data/evaluation/"
    "indicxlit_unseen_pipeline_v1.json"
)

EXPECTED = [
    "I need to go to the office today.",
    "They didn't come to the meeting yesterday.",
    "I haven't had lunch yet.",
    "She'll go to college tomorrow.",
    "I can't finish this task right now.",
    "I want coffee, but no sugar.",
    "Why didn't you call?",
    "He laughed at me.",
    "I'm very tired today.",
    "I have an interview tomorrow and I'm nervous.",
    "Don't delete that file.",
    "I don't understand this; please explain a little.",
]

SYSTEM = (
    "Translate this colloquial Tamil sentence into one "
    "natural English sentence. English words may appear "
    "inside Tamil text. Preserve subjects, negation, tense, "
    "questions, actions and emotions. Do not invent facts. "
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

    with urllib.request.urlopen(
        request, timeout=120
    ) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Existing first-run results: {OUTPUT}"
        )

    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = data["results"]

    assert len(rows) == len(EXPECTED) == 12

    results = []

    print("\nRIA-1 UNSEEN END-TO-END EVALUATION")
    print("=" * 60)

    for index, (row, expected) in enumerate(
        zip(rows, EXPECTED), 1
    ):
        prediction = ask_gemma(row["converted"])

        result = {
            "id": f"RIA-UNSEEN-{index:03d}",
            "original": row["original"],
            "converted_tamil": row["converted"],
            "expected_english": expected,
            "predicted_english": prediction,
            "evaluation_subset": (
                "known_benchmark_overlap"
                if index == 8
                else "development"
            ),
            "human_score": None,
        }

        results.append(result)

        print(f"\nTEST {index}")
        print("TANGLISH:", row["original"])
        print("TAMIL:", row["converted"])
        print("EXPECTED:", expected)
        print("RIA:", prediction)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "model": "gemma3:4b",
                "converter": "frozen_indicxlit_lexicon",
                "note": (
                    "Development test. Test 8 overlaps an "
                    "earlier held-out benchmark."
                ),
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

