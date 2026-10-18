
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OUT = ROOT / "ria1/data/expansion/batch_001.jsonl"

SCENARIOS = [
    # (tone, English user, Tamil user, Tanglish user)
    (
        "sad_stressed",
        "I prepared all week, but my presentation went badly.",
        "ஒரு வாரம் முழுக்க தயாரானேன், ஆனா என் பிரசன்டேஷன் சரியா போகல.",
        "Oru vaaram full-ah prepare pannen, aana presentation sariya pogala."
    ),
    (
        "happy_excited",
        "My first song just crossed a thousand plays!",
        "என் முதல் பாட்டு ஆயிரம் பிளேஸ் தாண்டிடுச்சு!",
        "En first song thousand plays thaandiduchu!"
    ),
    (
        "romantic_flirty",
        "Give me a cute, cheeky compliment!",
        "என்னை கொஞ்சம் கலாய்ச்சு ஒரு க்யூட் காம்ப்ளிமென்ட் சொல்லு!",
        "Enna konjam kalaaichu oru cute compliment sollu!"
    ),
    (
        "casual_friendly",
        "I'm free this weekend. Suggest something fun.",
        "இந்த வீக்கெண்ட் ஃப்ரீயா இருக்கேன். ஏதாவது ஜாலியா சொல்லு.",
        "Indha weekend free-ah irukken. Edhaavadhu jolly-ah sollu."
    ),
    (
        "confused_learning",
        "Explain APIs using a simple real-life example.",
        "API-ன்னா என்ன? ஒரு சிம்பிள் உதாரணத்தோட சொல்லு.",
        "API-na enna? Oru simple real-life example-oda sollu."
    ),
    (
        "frustrated_angry",
        "You keep misunderstanding my question, and it's annoying.",
        "நான் கேக்குறதை நீ திரும்ப திரும்ப தப்பா புரிஞ்சுக்கற. கடுப்பா இருக்கு.",
        "Naan kekkuradha nee thirumba thirumba thappa purinjukkura. Kadupa irukku."
    ),
    (
        "lonely_vulnerable",
        "Everyone has plans tonight, but I have no one to talk to.",
        "இன்னைக்கு எல்லாருக்கும் பிளான் இருக்கு. என்கிட்ட பேச யாரும் இல்ல.",
        "Innaiku ellarukkum plans irukku. Enkitta pesa yaarum illa."
    ),
]

LANGUAGES = ["english", "tamil", "tanglish"]


def main():
    if OUT.exists():
        raise FileExistsError(
            f"{OUT} already exists. "
            "Not overwriting a review batch."
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)

    records = []

    for index, (tone, *prompts) in enumerate(SCENARIOS, 1):
        for language, prompt in zip(LANGUAGES, prompts):
            record = {
                "id": f"ria1-b001-{index:02d}-{language}",
                "language": language,
                "tone": tone,
                "user_message": prompt,
                "assistant_response": "",
                "review_status": "draft",
                "source": "original_expansion_prompt",
                "batch": "001"
            }

            records.append(record)

    with OUT.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(
                    record, ensure_ascii=False
                ) + "\n"
            )

    print("\nRIA-1 EXPANSION BATCH 001")
    print("=" * 45)
    print("Created:", len(records))
    print("English:", 7)
    print("Tamil:", 7)
    print("Tanglish:", 7)
    print("Status: drafts, not training-approved")
    print("Saved:", OUT)


if __name__ == "__main__":
    main()

