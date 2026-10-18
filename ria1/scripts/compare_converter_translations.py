
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ria1/data/evaluation/generalization_v2_frozen"
OUTPUT = DATA / "converter_comparison_v1.jsonl"

MODEL = "translategemma:4b"
URL = "http://127.0.0.1:11434/api/chat"


def load_jsonl(filename):
    records = {}

    for line in (DATA / filename).read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip():
            continue

        record = json.loads(line)
        rid = record["id"]

        if rid in records:
            raise ValueError(f"Duplicate ID: {rid}")

        records[rid] = record

    return records


def translate(tamil):
    prompt = (
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

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 160,
            "num_ctx": 2048,
        },
        "keep_alive": "5m",
    }

    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=180
    ) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Results already exist: {OUTPUT}"
        )

    converter = load_jsonl(
        "dedicated_converter_diagnostic_v1.jsonl"
    )
    previous = load_jsonl(
        "translategemma_diagnostic_v1.jsonl"
    )
    answers = load_jsonl("answer_key.jsonl")

    assert len(converter) == 12
    assert set(converter) == set(previous)

    print("\nRIA-1 — MODULE 4.55")
    print("CONVERTER → TRANSLATEGEMMA COMPARISON")
    print("=" * 65)

    results = []

    for index, (rid, record) in enumerate(
        converter.items(), 1
    ):
        new_translation = translate(
            record["dedicated_tamil"]
        )

        result = {
            "id": rid,
            "original": record["original"],
            "expected": answers[rid]["expected_english"],
            "indicxlit_tamil": record["indicxlit_tamil"],
            "dedicated_tamil": record["dedicated_tamil"],
            "indicxlit_translation": previous[rid]["prediction"],
            "dedicated_translation": new_translation,
        }

        results.append(result)

        # Save every completed result for recovery.
        with OUTPUT.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    result, ensure_ascii=False
                ) + "\n"
            )

        print(f"\n{index}/12 — {rid}")
        print("EXPECTED:", result["expected"])
        print("INDICXLIT:", result["indicxlit_translation"])
        print("NEW ENGINE:", new_translation)

    print("\nCompleted:", len(results))
    print("Saved:", OUTPUT)
    print("Status: Awaiting human comparison")


if __name__ == "__main__":
    main()

