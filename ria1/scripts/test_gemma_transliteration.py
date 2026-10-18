
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

URL = "http://127.0.0.1:11434/api/chat"
MODEL = "gemma3:4b"

SYSTEM = """
Convert conversational Tanglish (Tamil written using
English letters) into natural colloquial Tamil script.

Rules:
- Do not translate the meaning into English.
- Preserve the original meaning, pronouns and tense.
- Preserve negation and questions.
- Preserve conversational Tamil rather than formal Tamil.
- English technical terms may remain in English.
- Return only the converted sentence.

Examples:
Tanglish: Enakku coffee vendaam.
Tamil: எனக்கு காபி வேண்டாம்.

Tanglish: Naan inniku office-ku pogala.
Tamil: நான் இன்னைக்கு ஆபீஸுக்கு போகல.

Tanglish: Aval konjam kovama irukka.
Tamil: அவள் கொஞ்சம் கோபமா இருக்கா.

Tanglish: Naalaikku vara mudiyuma?
Tamil: நாளைக்கு வர முடியுமா?
"""

TESTS = [
    "Amma inniku veetukku varala.",
    "Amma inniku veetukku pogala.",
    "Naan naalaikku college-ku varuven.",
    "Naan naalaikku college-ku poven.",
    "Avalukku indha food vendaam.",
    "Indha alavu saapadu podhum.",
    "Nethu avan call pannala.",
    "Inniku enakku velai mudiyala.",
    "Naalaikku vara mudiyuma?",
    "Aval konjam kovama irukka.",
    "Enakku ippo pesa thonala.",
    "Avan vara maattennu sonnaan.",
]


def ask(text):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 160,
        },
    }

    request = urllib.request.Request(
        URL,
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
    results = []

    print("\nRIA-1 GEMMA TANGLISH CONVERSION")
    print("=" * 55)

    for i, sentence in enumerate(TESTS, 1):
        converted = ask(sentence)

        print(f"\nTEST {i}")
        print("INPUT:", sentence)
        print("TAMIL:", converted)

        results.append({
            "id": f"RIA-CONVERT-{i:03d}",
            "input": sentence,
            "converted": converted,
        })

    output = (
        ROOT / "ria1/data/evaluation/"
        "gemma_transliteration_v1.json"
    )

    if output.exists():
        raise FileExistsError(
            "Evaluation file already exists. "
            "Do not overwrite the original results."
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


if __name__ == "__main__":
    main()

