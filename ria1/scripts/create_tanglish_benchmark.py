
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ria1/data/evaluation/tanglish_comprehension_v1.jsonl"

# Each case: category, user message, intended meaning.
CASES = [
    ("pronoun", "Naan oru pudhu paattu compose pannen. Epdi improve pannalaam?",
     "The user composed a new song and wants advice on improving it."),
    ("pronoun", "Naan innaiku romba tired-ah irukken.",
     "The user is tired today."),
    ("pronoun", "Naan first prize win pannitten!",
     "The user won first prize."),
    ("pronoun", "Naan sapten, aana innum pasikkudhu.",
     "The user ate but is still hungry."),
    ("pronoun", "Naan unna oru doubt kekkava?",
     "The user wants to ask Ria a question."),

    ("emotion", "Enakku romba kadupa irukku.",
     "The user is frustrated or angry."),
    ("emotion", "Innaiku konjam lonely-ah feel panren.",
     "The user feels lonely."),
    ("emotion", "Enakku bayama irukku interview-ku.",
     "The user feels nervous about an interview."),
    ("emotion", "Semma happy-ah irukken!",
     "The user is very happy."),
    ("emotion", "Ellame thappa pogura maari irukku.",
     "The user feels overwhelmed or discouraged."),

    ("intent", "En Python code work aagala. Help pannuva?",
     "The user wants help debugging Python code."),
    ("intent", "Oru cute love song lyrics idea sollu.",
     "The user wants a romantic songwriting idea."),
    ("intent", "Enakku ML basics simple-ah explain pannu.",
     "The user wants a simple machine-learning explanation."),
    ("intent", "Naalaikku interview irukku. Prepare panna help pannu.",
     "The user wants interview preparation help."),
    ("intent", "Enakku oru easy guitar practice routine venum.",
     "The user wants a beginner guitar practice routine."),

    ("context", "Nee naan sonnadha purinjukittiya?",
     "The user asks whether Ria understood them."),
    ("context", "Nethu pesinadhu unakku nyabagam irukka?",
     "The user asks whether Ria remembers yesterday's conversation."),
    ("context", "Adha konjam short-ah sollu.",
     "The user requests a shorter answer; 'adha' needs earlier context."),
    ("context", "Idhula first step enna?",
     "The user asks about the first step; 'idhula' needs context."),
    ("context", "Nee already idha check pannitiya?",
     "The user asks whether Ria actually checked something."),

    ("correction", "Nee thappa purinjukitta. Naan adha sollala.",
     "The user corrects Ria's misunderstanding."),
    ("correction", "Tamil-la pesu, English-la vendaam.",
     "The user requests Tamil instead of English."),
    ("correction", "Romba formal-ah irukku. Casual-ah pesu.",
     "The user wants a more casual speaking style."),
    ("correction", "Naan song pathi sonnen, food pathi illa.",
     "The user is talking about a song, not food."),
    ("correction", "Enakku advice vendaam, konjam listen pannu.",
     "The user wants empathy and listening, not advice."),

    ("ambiguity", "Naan bread sapten.",
     "The user ate naan bread."),
    ("ambiguity", "Naan naan sapten.",
     "The user says they ate naan bread; first 'naan' means 'I'."),
    ("ambiguity", "Avan enna paathu sirichaan.",
     "A male person laughed or smiled while looking at the user."),
    ("ambiguity", "Enakku light-ah headache irukku.",
     "The user has a mild headache; 'light-ah' means mildly."),
    ("ambiguity", "En phone hang aagudhu.",
     "The user's phone is freezing or becoming unresponsive."),
]


def main():
    if OUT.exists():
        raise FileExistsError(
            "Benchmark already exists. "
            "Refusing to overwrite evaluation data."
        )

    assert len(CASES) == 30

    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8") as file:
        for index, (category, prompt, meaning) in enumerate(
            CASES, 1
        ):
            record = {
                "id": f"RIA-TC-{index:03d}",
                "category": category,
                "language": "tanglish",
                "user_message": prompt,
                "expected_meaning": meaning,
                "split": "held_out_test",
            }

            file.write(
                json.dumps(record, ensure_ascii=False)
                + "\n"
            )

    print("RIA-1 TANGLISH BENCHMARK")
    print("=" * 45)
    print("Cases:", len(CASES))
    print("Categories:", 6)
    print("Purpose: Evaluation only")
    print("Saved:", OUT)


if __name__ == "__main__":
    main()

