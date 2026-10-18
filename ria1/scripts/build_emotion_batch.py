
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = (
    ROOT / "ria1/data/language_foundation/"
    "emotion_intent_001.jsonl"
)

CASES = [
    ("Innaiku oru nalla news kedaichuchu, unkitte share pannanum!",
     "The user received good news and wants to share it."),
    ("En project select aayiduchu! Romba sandhoshama irukku.",
     "The user's project was selected and they feel very happy."),
    ("En friend enakku surprise gift kuduthaan!",
     "The user's friend gave them a surprise gift."),
    ("Naan romba naala wait panna opportunity kedaichiduchu.",
     "The user finally received an opportunity they had waited for."),
    ("Indha achievement-ah konjam celebrate pannalaam!",
     "The user wants to celebrate an achievement."),

    ("Full day try panniyum indha bug fix aagala. Erichala irukku.",
     "The user is irritated because they could not fix a bug."),
    ("Same mistake thirumba nadandhuduchu. Romba frustrate aagudhu.",
     "The user feels frustrated because the same mistake happened again."),
    ("Nee enna interrupt pannadha, first naan solradha kelu.",
     "The user wants Ria to stop interrupting and listen first."),
    ("Plan pannadhellam last minute-la change aayiduchu. Kadupa irukku.",
     "The user is angry because their plans changed at the last minute."),
    ("En question-ku straight answer sollu, suththi pesaadha.",
     "The user wants a direct answer without unnecessary explanation."),

    ("Innaiku enakku edhuvum panna thonala.",
     "The user does not feel like doing anything today."),
    ("Neraya effort potten, aana yaarum appreciate pannala.",
     "The user feels unappreciated despite putting in effort."),
    ("Konjam manasu kashtama irukku, unkitta pesanum.",
     "The user feels emotionally upset and wants to talk."),
    ("Naan expect panna result kedaikkala. Disappointed-ah irukken.",
     "The user is disappointed about not getting the expected result."),
    ("Innaiku konjam silent-ah irukkanum pola irukku.",
     "The user feels like being quiet today."),

    ("Pudhu team-kooda work panna konjam nervous-ah irukku.",
     "The user feels nervous about working with a new team."),
    ("Presentation start panna munnaadi heart fast-ah beat aagudhu.",
     "The user feels anxious before starting a presentation."),
    ("En decision correct-ah irukkuma nu doubt-ah irukku.",
     "The user is uncertain whether their decision is right."),
    ("First day office-ku poren, konjam tension-ah irukku.",
     "The user feels nervous about their first day at the office."),
    ("Edhavadhu mistake panniduveno nu bayama irukku.",
     "The user is afraid they might make a mistake."),

    ("Ellarum busy-ah irukkaanga, yaaravadhu kooda pesa aasaiya irukku.",
     "The user wishes they had someone to talk with."),
    ("Naan solradha yaarum serious-ah eduthukka maatraanga.",
     "The user feels that nobody takes what they say seriously."),
    ("Innaiku advice laam vendaam, konjam casual-ah pesalaam.",
     "The user wants casual conversation rather than advice."),
    ("Enakku ippo solution venam, konjam support podhum.",
     "The user wants emotional support, not a solution right now."),
    ("Naan pesuradha mudhal-la full-ah ketuttu apram respond pannu.",
     "The user wants Ria to listen fully before responding."),
]


def main():
    if OUT.exists():
        raise FileExistsError(
            f"Batch already exists: {OUT}"
        )

    assert len(CASES) == 25

    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8") as file:
        for index, (user, meaning) in enumerate(CASES, 1):
            record = {
                "id": f"RIA-LF-EI-{index:03d}",
                "category": "emotion_intent",
                "language": "tanglish",
                "user_message": user,
                "english_meaning": meaning,
                "tamil_equivalent": "",
                "ria_response": "",
                "review_status": "draft",
                "source": "original_language_authoring",
            }
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    print("\nRIA-1 EMOTION & INTENT BATCH")
    print("=" * 45)
    print("Draft records:", len(CASES))
    print("Approved: 0")
    print("Saved:", OUT)


if __name__ == "__main__":
    main()

