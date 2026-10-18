
import json
from pathlib import Path
from ria1.scripts.test_dynamic_grounding import ask_gemma

ROOT = Path(__file__).resolve().parents[2]

SYSTEM = """
You understand conversational Tamil.

Translate the user's sentence into one concise,
natural English sentence.

Preserve:
- Who is performing the action
- Come versus go
- Past, present, future
- Negation and questions
- Emotional meaning

Do not add people, objects or events.
Do not answer the user's request.
Return only the translation.
"""

TESTS = [
    (
        "Amma inniku veetukku varala.",
        "அம்மா இன்னைக்கு வீட்டுக்கு வரல.",
        "Mom didn't come home today."
    ),
    (
        "Amma inniku veetukku pogala.",
        "அம்மா இன்னைக்கு வீட்டுக்கு போகல.",
        "Mom didn't go home today."
    ),
    (
        "Naan naalaikku college-ku varuven.",
        "நான் நாளைக்கு காலேஜுக்கு வருவேன்.",
        "I'll come to college tomorrow."
    ),
    (
        "Naan naalaikku college-ku poven.",
        "நான் நாளைக்கு காலேஜுக்கு போவேன்.",
        "I'll go to college tomorrow."
    ),
    (
        "Avalukku indha food vendaam.",
        "அவளுக்கு இந்த சாப்பாடு வேண்டாம்.",
        "She doesn't want this food."
    ),
    (
        "Indha alavu saapadu podhum.",
        "இந்த அளவு சாப்பாடு போதும்.",
        "This amount of food is enough."
    ),
    (
        "Nethu avan call pannala.",
        "நேத்து அவன் கால் பண்ணல.",
        "He didn't call yesterday."
    ),
    (
        "Inniku enakku velai mudiyala.",
        "இன்னைக்கு எனக்கு வேலை முடியல.",
        "I couldn't finish my work today."
    ),
    (
        "Naalaikku vara mudiyuma?",
        "நாளைக்கு வர முடியுமா?",
        "Can you come tomorrow?"
    ),
    (
        "Aval konjam kovama irukka.",
        "அவள் கொஞ்சம் கோபமா இருக்கா.",
        "She's a little angry."
    ),
    (
        "Enakku ippo pesa thonala.",
        "எனக்கு இப்போ பேசத் தோணல.",
        "I don't feel like talking right now."
    ),
    (
        "Avan vara maattennu sonnaan.",
        "அவன் வர மாட்டேன்னு சொன்னான்.",
        "He said he wouldn't come."
    ),
]


def main():
    output = (
        ROOT / "ria1/data/evaluation/"
        "tamil_script_diagnostic_v1.json"
    )

    if output.exists():
        raise FileExistsError(
            "First-run results already exist. "
            "Do not overwrite them."
        )

    results = []

    print("\nRIA-1 TAMIL SCRIPT COMPARISON")
    print("=" * 55)

    for number, (tanglish, tamil, expected) in enumerate(TESTS, 1):
        tanglish_answer = ask_gemma(
            SYSTEM, tanglish
        )

        tamil_answer = ask_gemma(
            SYSTEM, tamil
        )

        print(f"\nTEST {number}")
        print("TANGLISH:", tanglish)
        print("TAMIL:", tamil)
        print("EXPECTED:", expected)
        print("ROMANIZED OUTPUT:", tanglish_answer)
        print("TAMIL OUTPUT:", tamil_answer)

        results.append({
            "id": f"RIA-SCRIPT-{number:03d}",
            "tanglish": tanglish,
            "tamil": tamil,
            "expected": expected,
            "romanized_output": tanglish_answer,
            "tamil_output": tamil_answer,
            "human_review": "pending"
        })

    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(
            {
                "model": "gemma3:4b",
                "experiment": "paired_script_comparison",
                "tests": results,
            },
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("\nSaved:", output)
    print("Manual scoring required.")


if __name__ == "__main__":
    main()

