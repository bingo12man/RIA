
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = (
    ROOT / "ria1/data/language_foundation/"
    "pronouns_verbs_001.jsonl"
)

# Original authoring prompts. Not automatically approved.
CASES = [
    ("Naan innaiku office-ku late-ah vandhen.",
     "I arrived late at the office today."),
    ("Nee enakku konjam help pannuva?",
     "Can you help me a little?"),
    ("Avan nethu enakku call pannaan.",
     "He called me yesterday."),
    ("Ava innaiku leave eduthirukka.",
     "She has taken leave today."),
    ("Naanga weekend trip plan panrom.",
     "We are planning a weekend trip."),
    ("Neenga enga poringa?",
     "Where are you going?"),
    ("Avanga already vandhutaanga.",
     "They have already arrived."),
    ("Naan saapadu ready pannitten.",
     "I have prepared the food."),
    ("Nee sonnadhu enakku puriyala.",
     "I didn't understand what you said."),
    ("En friend enakku message anuppinaan.",
     "My friend sent me a message."),
    ("Naan ippo dhaan ezhundhen.",
     "I just woke up."),
    ("Nee eppo thirumbi varuva?",
     "When will you come back?"),
    ("Avan enna paathu pesinaan.",
     "He spoke to me."),
    ("Ava enna wait panna sonna.",
     "She asked me to wait."),
    ("Naanga innum start pannala.",
     "We haven't started yet."),
    ("Naan daily konjam guitar practice panren.",
     "I practice guitar a little every day."),
    ("Nee indha question-ku answer sollu.",
     "Answer this question."),
    ("Avanga enna invite pannanga.",
     "They invited me."),
    ("Naan unakku oru idea solren.",
     "I'll tell you an idea."),
    ("Enakku innoru chance kedaichirukku.",
     "I have received another chance."),
    ("Nee enna kekkura nu puriyudhu.",
     "I understand what you're asking."),
    ("Naan idha munnaadi try pannirukken.",
     "I have tried this before."),
    ("Naama rendu perum serndhu plan pannalaam.",
     "We can plan together."),
    ("En thambi innaiku exam ezhudhuraan.",
     "My younger brother is taking an exam today."),
    ("En akka enakku advice kuduthaanga.",
     "My older sister gave me advice."),
]


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Batch already exists: {OUTPUT}"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8") as file:
        for index, (user, meaning) in enumerate(CASES, 1):
            record = {
                "id": f"RIA-LF-PV-{index:03d}",
                "category": "pronouns_verbs",
                "language": "tanglish",
                "user_message": user,
                "english_meaning": meaning,
                "tamil_equivalent": "",
                "ria_response": "",
                "review_status": "draft",
                "source": "original_language_authoring",
            }

            file.write(
                json.dumps(
                    record, ensure_ascii=False
                ) + "\n"
            )

    print("\nRIA-1 LANGUAGE FOUNDATION")
    print("=" * 45)
    print("Category: Pronouns and verbs")
    print("Draft records:", len(CASES))
    print("Approved:", 0)
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()

