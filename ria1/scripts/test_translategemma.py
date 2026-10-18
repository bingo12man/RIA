
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ria1/data/evaluation/generalization_v2_frozen"

MODEL = "translategemma:4b"
URL = "http://127.0.0.1:11434/api/chat"

TEST_IDS = [
    "RIA-GEN2-001",
    "RIA-GEN2-002",
    "RIA-GEN2-007",
    "RIA-GEN2-008",
    "RIA-GEN2-009",
    "RIA-GEN2-011",
    "RIA-GEN2-016",
    "RIA-GEN2-020",
    "RIA-GEN2-025",
    "RIA-GEN2-027",
    "RIA-GEN2-030",
    "RIA-GEN2-031",
]


def load(path):
    return {
        r["id"]: r
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for r in [json.loads(line)]
    }


def translate(tamil):
    instruction = (
        "You are a professional Tamil (ta) to English (en) "
        "translator. Your goal is to accurately convey "
        "the meaning and nuances of the original Tamil "
        "text while adhering to English grammar, "
        "vocabulary, and cultural sensitivities. "
        "Produce only the English translation, without "
        "any additional explanations or commentary. "
        "Please translate the following Tamil text into "
        "English:\n\n\n" + tamil
    )

    body = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": instruction}
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 160,
            "num_ctx": 2048,
        },
        "keep_alive": "0s",
    }

    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=180) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    prompts = load(DATA / "prompts.jsonl")
    answers = load(DATA / "answer_key.jsonl")
    conversions = load(DATA / "conversions_v1.jsonl")

    output = DATA / "translategemma_diagnostic_v1.jsonl"

    if output.exists():
        raise FileExistsError(
            "Diagnostic results already exist; refusing overwrite."
        )

    results = []

    print("\nRIA-1 — MODULE 4.51")
    print("TRANSLATEGEMMA DIAGNOSTIC")
    print("=" * 60)

    for i, rid in enumerate(TEST_IDS, 1):
        original = prompts[rid]["user_message"]
        expected = answers[rid]["expected_english"]
        tamil = conversions[rid]["top1_tamil"]

        prediction = translate(tamil)

        print(f"\n{i}/{len(TEST_IDS)} — {rid}")
        print("TANGLISH:", original)
        print("TAMIL:", tamil)
        print("EXPECTED:", expected)
        print("TRANSLATEGEMMA:", prediction)

        results.append({
            "id": rid,
            "original": original,
            "tamil": tamil,
            "expected": expected,
            "prediction": prediction,
        })

    # Exclusive creation protects earlier runs.
    with output.open("x", encoding="utf-8") as f:
        for record in results:
            f.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    print("\nCompleted:", len(results))
    print("Saved:", output)
    print("Status: Requires independent human scoring")


if __name__ == "__main__":
    main()

