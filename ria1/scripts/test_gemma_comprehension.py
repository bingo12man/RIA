
import json
import urllib.request
import urllib.error

MODEL = "gemma3:4b"
URL = "http://127.0.0.1:11434/api/chat"

SYSTEM = (
    "You are a Tamil language comprehension assistant. "
    "The input is conversational Tamil written in English "
    "letters, also called Tanglish. "
    "Return ONLY one short English sentence explaining "
    "the meaning. Do not explain word by word. "
    "Do not answer requests. Preserve negation and tense."
)

TESTS = [
    (
        "Enakku coffee vendaam, tea podhum.",
        "I don't want coffee; tea is enough."
    ),
    (
        "Enakku tea vendaam, coffee podhum.",
        "I don't want tea; coffee is enough."
    ),
    (
        "Naan inniku office-ku pogala.",
        "I didn't go to the office today."
    ),
    (
        "Enakku konjam bayama irukku.",
        "I'm feeling a little scared or nervous."
    ),
]


def ask_model(sentence):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": "Current user: " + sentence
            },
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
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    print("\nRIA-1 GEMMA COMPREHENSION TEST")
    print("=" * 55)

    for index, (sentence, expected) in enumerate(TESTS, 1):
        print(f"\nTEST {index}")
        print("INPUT:", sentence)
        print("EXPECTED:", expected)

        try:
            actual = ask_model(sentence)
            print("GEMMA:", actual)
        except (urllib.error.URLError, TimeoutError) as e:
            print("ERROR:", e)
            break

    print("\nReview the answers for meaning accuracy.")


if __name__ == "__main__":
    main()

