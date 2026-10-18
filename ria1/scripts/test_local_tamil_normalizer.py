
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ria1/data/evaluation/generalization_v2_frozen"

OUTPUT = DATA / "local_normalizer_diagnostic_v1.jsonl"
OLLAMA = "http://127.0.0.1:11434/api/chat"

NORMALIZER = "gemma3:4b"
TRANSLATOR = "translategemma:4b"

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


def load_jsonl(filename):
    result = {}

    for line in (DATA / filename).read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip():
            continue

        row = json.loads(line)

        if row["id"] in result:
            raise ValueError(
                f"Duplicate ID: {row['id']}"
            )

        result[row["id"]] = row

    return result


def ask(model, prompt):
    body = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 200,
            "num_ctx": 2048
        },
        # Unload between stages to reduce memory use.
        "keep_alive": "0s"
    }

    request = urllib.request.Request(
        OLLAMA,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(
        request, timeout=240
    ) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def normalize_tamil(tanglish):
    instruction = f"""
Convert the following colloquial Tanglish sentence into
natural, readable Tamil script.

This is a SCRIPT CONVERSION task, not translation.

Requirements:
- Keep the exact original meaning.
- Preserve speakers and pronouns.
- Preserve negative words and prohibitions.
- Preserve past, present and future tense.
- Preserve questions, commands and requests.
- Preserve timing and quantities.
- Keep common technical English words when needed.
- Use correct, familiar Tamil spelling.
- Do not add subjects or facts absent from the input.
- Do not answer the sentence.
- Return ONLY the Tamil-script sentence.

Tanglish:
{tanglish}

Tamil:
""".strip()

    return ask(NORMALIZER, instruction)


def translate_tamil(tamil):
    instruction = (
        "You are a professional Tamil (ta) to English (en) "
        "translator. Translate accurately into natural English. "
        "Preserve pronouns, subjects, tense, negation, questions, "
        "requests, actions and quantities. "
        "Do not explain or answer the request. "
        "Return only the English translation.\n\n"
        + tamil
    )

    return ask(TRANSLATOR, instruction)


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Output already exists: {OUTPUT}"
        )

    prompts = load_jsonl("prompts.jsonl")
    answers = load_jsonl("answer_key.jsonl")
    previous = load_jsonl("translategemma_diagnostic_v1.jsonl")

    results = []

    print("\nRIA-1 — MODULE 4.53")
    print("AUTOMATIC TAMIL NORMALIZATION DIAGNOSTIC")
    print("=" * 65)

    for index, rid in enumerate(TEST_IDS, 1):
        original = prompts[rid]["user_message"]
        expected = answers[rid]["expected_english"]

        converted = normalize_tamil(original)

        if not re.search(r"[\u0B80-\u0BFF]", converted):
            prediction = ""
            error = "Normalizer did not produce Tamil script"
        else:
            prediction = translate_tamil(converted)
            error = None

        result = {
            "id": rid,
            "original": original,
            "automatic_tamil": converted,
            "expected": expected,
            "previous_raw_translation": previous[rid]["prediction"],
            "automatic_translation": prediction,
            "error": error
        }

        results.append(result)

        # Append immediately so interrupted runs
        # retain completed diagnostic records.
        with OUTPUT.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    result, ensure_ascii=False
                ) + "\n"
            )

        print(f"\n{index}/12 — {rid}")
        print("INPUT:", original)
        print("AUTOMATIC TAMIL:", converted)
        print("EXPECTED:", expected)
        print("AUTOMATIC TRANSLATION:", prediction)

        if error:
            print("WARNING:", error)

    print("\nCompleted:", len(results))
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()

