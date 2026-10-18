
import json
import math
import re
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA = (
    ROOT / "ria1/data/releases/"
    "language_foundation_v1/meaning_reference.jsonl"
)

MODEL = "gemma3:4b"
URL = "http://127.0.0.1:11434/api/chat"

# Manually defined starter vocabulary.
# These rules are reference knowledge, not learned weights.
GLOSSARY = {
    "enakku": "to me / for me",
    "vendaam": "do not want / not needed",
    "vendam": "do not want / not needed",
    "podhum": "enough / sufficient",
    "naan": "I (Tamil pronoun, not bread)",
    "inniku": "today",
    "netru": "yesterday",
    "naalaikku": "tomorrow",
    "pogala": "did not go",
    "varala": "did not come",
    "mudiyadhu": "cannot / not possible",
    "konjam": "a little",
    "bayama": "scared / afraid",
    "irukku": "is / exists / feeling, context dependent",
    "avan": "he",
    "aval": "she",
    "mattum": "only",
    "aana": "but",
}

STOPWORDS = {
    "the", "and", "but", "for", "with", "user",
    "current", "previous", "please", "enna",
    "oru", "idhu", "adhu",
}


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def load_approved():
    with DATA.open(encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


def retrieve_examples(query, records, limit=3):
    docs = []

    for record in records:
        words = set(tokens(record["tanglish"]))
        words -= STOPWORDS
        docs.append(words)

    df = Counter()

    for words in docs:
        df.update(words)

    n = len(records)
    query_words = set(tokens(query)) - STOPWORDS
    matches = []

    for record, words in zip(records, docs):
        # Do not supply an exact answer from the
        # approved examples for an identical input.
        if tokens(record["tanglish"]) == tokens(query):
            continue

        shared = query_words & words

        if not shared:
            continue

        score = sum(
            math.log((n + 1) / (df[w] + 1)) + 1
            for w in shared
        )

        # Encourage more relevant words to match.
        score *= len(shared) / max(1, len(query_words))

        matches.append((score, record))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in matches[:limit]]


def build_system(query, records):
    words = set(tokens(query))

    matched_glossary = [
        f"{word} = {meaning}"
        for word, meaning in GLOSSARY.items()
        if word in words
    ]

    examples = retrieve_examples(query, records)

    sections = [
        "You are a Tamil/Tanglish comprehension assistant.",
        "Translate the user's intended meaning into exactly "
        "one concise English sentence.",
        "Preserve negation, tense, pronouns and emotions.",
        "Do not add facts or answer the user's request.",
        "Interpret the complete sentence using context.",
    ]

    if matched_glossary:
        sections.append(
            "\nRELEVANT VOCABULARY:\n"
            + "\n".join(matched_glossary)
        )

    if examples:
        lines = []

        for row in examples:
            lines.append(
                "Tanglish: " + row["tanglish"]
                + "\nMeaning: " + row["english_meaning"]
            )

        sections.append(
            "\nREFERENCE EXAMPLES:\n"
            + "\n\n".join(lines)
        )

    return "\n\n".join(sections), matched_glossary, examples


def ask_gemma(system, query):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
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
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=120
    ) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    records = load_approved()

    # Known diagnostic cases. These are NOT a blind benchmark.
    tests = [
        "Enakku coffee vendaam, tea podhum.",
        "Enakku tea vendaam, coffee podhum.",
        "Naan inniku office-ku pogala.",
        "Enakku konjam bayama irukku.",
        "Avan netru school-ku varala.",
        "Naalaikku meeting-ku vara mudiyadhu.",
    ]

    results = []

    print("\nRIA-1 DYNAMIC GROUNDING TEST")
    print("=" * 55)
    print("Approved reference examples:", len(records))

    for i, query in enumerate(tests, 1):
        system, glossary, examples = build_system(
            query, records
        )

        response = ask_gemma(system, query)

        print(f"\nTEST {i}")
        print("INPUT:", query)
        print("GLOSSARY:", glossary)
        print(
            "RETRIEVED:",
            [r["id"] for r in examples]
        )
        print("RIA:", response)

        results.append({
            "input": query,
            "glossary": glossary,
            "retrieved_ids": [r["id"] for r in examples],
            "response": response,
        })

    output = (
        ROOT / "ria1/data/evaluation/"
        "dynamic_grounding_diagnostic.json"
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nSaved:", output)


if __name__ == "__main__":
    main()

