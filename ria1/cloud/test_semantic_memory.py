from ria1.cloud.semantic_memory import (
    semantic_retrieve,
    THRESHOLD,
)

MEMORIES = {
    "instrument": "guitar",
}

CASES = [
    ("What instrument am I learning?", True),
    ("What musical instrument do I practice?", True),
    ("Help me with my guitar chords.", True),
    ("My strumming needs improvement.", True),
    ("How can I practice music better?", True),

    ("I'm struggling.", False),
    ("I'm confused about my next step.", False),
    ("My Python application keeps crashing.", False),
    ("What is a Python dictionary?", False),
    ("I'm nervous about my job interview.", False),
    ("Tell me about Bengaluru.", False),
    ("I feel tired today.", False),
]


def main():
    print("RIA SEMANTIC MEMORY DIAGNOSTIC")
    print("Threshold:", THRESHOLD)
    print()

    correct = 0

    for message, expected in CASES:
        matches = semantic_retrieve(message, MEMORIES)
        selected = bool(matches)

        passed = selected == expected
        correct += int(passed)

        score = matches[0]["score"] if matches else "below threshold"

        print(
            "PASS" if passed else "FAIL",
            "|", message,
            "| score:", score,
            "| selected:", selected,
        )

    print()
    print("Diagnostic matches:", correct, "/", len(CASES))
    print(
        "This is retrieval accuracy on a small synthetic test, "
        "not an overall conversation-quality score."
    )


if __name__ == "__main__":
    main()
