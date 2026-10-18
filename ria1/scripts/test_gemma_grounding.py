
import json
import urllib.request

URL = "http://127.0.0.1:11434/api/chat"
MODEL = "gemma3:4b"

BASE_SYSTEM = """
You understand colloquial Tamil written in English letters
(Tanglish). Translate the meaning of the current user's
sentence into one concise English sentence.

Preserve negation, tense, and emotions.
Return only the English meaning.
Do not answer the user's request.
"""

GROUNDED_SYSTEM = BASE_SYSTEM + """

Use this small Tanglish vocabulary reference:

enakku = to me / for me
vendaam = don't want / not needed
podhum = enough / sufficient
naan = I
inniku = today
pogala = did not go
konjam = a little
bayama irukku = feeling scared or nervous

Important:
- "vendaam" expresses refusal or negation.
- "-la" can express past negation in colloquial verbs,
  depending on context.
- Do not mistake "naan" for bread.
- Interpret the full sentence, not just individual words.
"""

TESTS = [
    {
        "input": "Enakku coffee vendaam, tea podhum.",
        "expected": "I don't want coffee; tea is enough.",
        "type": "glossary-covered",
    },
    {
        "input": "Enakku tea vendaam, coffee podhum.",
        "expected": "I don't want tea; coffee is enough.",
        "type": "glossary-covered",
    },
    {
        "input": "Naan inniku office-ku pogala.",
        "expected": "I didn't go to the office today.",
        "type": "glossary-covered",
    },
    {
        "input": "Enakku konjam bayama irukku.",
        "expected": "I'm feeling a little scared or nervous.",
        "type": "glossary-covered",
    },
    {
        "input": "Avan netru school-ku varala.",
        "expected": "He didn't come to school yesterday.",
        "type": "partially-covered",
    },
    {
        "input": "Naalaikku meeting-ku vara mudiyadhu.",
        "expected": "I won't be able to attend tomorrow's meeting.",
        "type": "unseen-vocabulary",
    },
]


def generate(sentence, system):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": sentence},
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 100,
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
        data = json.load(response)

    return data["message"]["content"].strip()


def main():
    results = []

    print("\nRIA-1 GEMMA LANGUAGE GROUNDING")
    print("=" * 60)

    for i, test in enumerate(TESTS, 1):
        print(f"\nTEST {i}: {test['type']}")
        print("INPUT:", test["input"])
        print("EXPECTED:", test["expected"])

        baseline = generate(
            test["input"], BASE_SYSTEM
        )
        grounded = generate(
            test["input"], GROUNDED_SYSTEM
        )

        print("BASELINE:", baseline)
        print("GROUNDED:", grounded)

        results.append({
            **test,
            "baseline": baseline,
            "grounded": grounded,
        })

    output = (
        "ria1/data/evaluation/"
        "gemma_grounding_diagnostic.json"
    )

    from pathlib import Path

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nSaved:", output)
    print("Human scoring required.")


if __name__ == "__main__":
    main()

