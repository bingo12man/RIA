
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ria1/data/evaluation/generalization_v2_frozen"

MODEL = "translategemma:4b"
URL = "http://127.0.0.1:11434/api/chat"

# Human-corrected diagnostic Tamil.
# These are not machine-generated transliterations.
CORRECTED = {
    "RIA-GEN2-001": "இந்த பார்சலைத் திறக்கக் கூடாது.",
    "RIA-GEN2-002": "எனக்கு இப்போ சாப்பிட இஷ்டம் இல்லை.",
    "RIA-GEN2-007": "நான் வருவதற்குள் அவர்கள் கிளம்பிவிட்டார்கள்.",
    "RIA-GEN2-008": "மீட்டிங் முடிந்த பிறகு பேசலாம்.",
    "RIA-GEN2-009": "அவள் சொன்னதை அவனிடம் சொல்லாதே.",
    "RIA-GEN2-011": "என் தம்பி இன்னிக்கு லேட்டாக வருவான்.",
    "RIA-GEN2-016": "நீ உறுதிப்படுத்திவிட்டாயா இல்லையா?",
    "RIA-GEN2-020": "நான் யாரையும் தொந்தரவு செய்ய விரும்பவில்லை.",
    "RIA-GEN2-025": "எனக்கு அது சரியாகப் புரியவில்லை.",
    "RIA-GEN2-027": "உங்களை எங்கேயோ பார்த்த மாதிரி இருக்கிறது.",
    "RIA-GEN2-030": "மழை பெய்தால் வெளியே போக வேண்டாம்.",
    "RIA-GEN2-031": "ஒரு மணி நேரம் கழித்து எனக்கு நினைவூட்டு.",
}


def load_jsonl(filename):
    return {
        row["id"]: row
        for line in (DATA / filename).read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
        for row in [json.loads(line)]
    }


def translate(tamil):
    instruction = (
        "You are a professional Tamil (ta) to English (en) "
        "translator. Translate the following Tamil text "
        "accurately into natural English. Preserve people, "
        "negation, tense, requests, and questions. "
        "Return only the translation.\n\n"
        + tamil
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": instruction}
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 160,
            "num_ctx": 2048
        },
        "keep_alive": "5m"
    }

    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(
        request, timeout=180
    ) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    prompts = load_jsonl("prompts.jsonl")
    answers = load_jsonl("answer_key.jsonl")
    conversions = load_jsonl("conversions_v1.jsonl")
    previous = load_jsonl("translategemma_diagnostic_v1.jsonl")

    output = DATA / "corrected_tamil_diagnostic_v1.jsonl"

    if output.exists():
        raise FileExistsError(
            "Previous diagnostic exists; refusing overwrite."
        )

    results = []

    print("\nRIA-1 — MODULE 4.52")
    print("CORRECTED TAMIL DIAGNOSTIC")
    print("=" * 60)

    for index, (rid, corrected) in enumerate(
        CORRECTED.items(), 1
    ):
        original = prompts[rid]["user_message"]
        expected = answers[rid]["expected_english"]
        raw_tamil = conversions[rid]["top1_tamil"]
        old_prediction = previous[rid]["prediction"]

        new_prediction = translate(corrected)

        print(f"\n{index}/12 — {rid}")
        print("TANGLISH:", original)
        print("RAW TAMIL:", raw_tamil)
        print("CORRECTED TAMIL:", corrected)
        print("EXPECTED:", expected)
        print("OLD TRANSLATION:", old_prediction)
        print("NEW TRANSLATION:", new_prediction)

        results.append({
            "id": rid,
            "original": original,
            "raw_tamil": raw_tamil,
            "corrected_tamil": corrected,
            "expected": expected,
            "old_translation": old_prediction,
            "new_translation": new_prediction,
        })

    with output.open("x", encoding="utf-8") as f:
        for row in results:
            f.write(
                json.dumps(row, ensure_ascii=False) + "\n"
            )

    print("\n" + "=" * 60)
    print("Completed:", len(results))
    print("Saved:", output)
    print("Status: Human comparison required")


if __name__ == "__main__":
    main()

