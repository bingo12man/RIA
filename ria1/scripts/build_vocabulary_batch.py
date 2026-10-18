
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = (
    ROOT / "ria1/data/language_foundation/"
    "everyday_vocabulary_001.jsonl"
)

CASES = [
    ("Indha velai mudikka romba neram aagudhu.",
     "This work is taking a long time."),
    ("Saapadu saapida time aayiduchu.",
     "It's time to eat."),
    ("Enakku konjam thookam varudhu.",
     "I'm feeling a little sleepy."),
    ("Innaiku climate romba nalla irukku.",
     "The weather is very nice today."),
    ("Nethu full-ah mazha peinjuchu.",
     "It rained throughout yesterday."),
    ("En bag enga vechen nu theriyala.",
     "I don't know where I put my bag."),
    ("Indha shirt enakku pudichirukku.",
     "I like this shirt."),
    ("Enakku oru coffee kudikkanum pola irukku.",
     "I feel like having a coffee."),
    ("Konjam medhuva pesu.",
     "Speak a little slowly."),
    ("Indha road-la traffic adhigama irukku.",
     "There's heavy traffic on this road."),
    ("Innaiku enakku romba velai irukku.",
     "I have a lot of work today."),
    ("Indha idea nalla irukku nu thonudhu.",
     "I think this idea is good."),
    ("Enakku indha matter puriyave illa.",
     "I don't understand this matter at all."),
    ("Konjam yosichu solren.",
     "I'll think about it and tell you."),
    ("Enakku idhu konjam kashtama irukku.",
     "This is a little difficult for me."),
    ("Innum konjam neram venum.",
     "I need a little more time."),
    ("Indha paattu kekka nalla irukku.",
     "This song sounds nice."),
    ("Enna panradhu nu theriyama irukken.",
     "I don't know what to do."),
    ("Adha marandhuten, nyabagam varala.",
     "I forgot that and can't remember it."),
    ("Nee solradhu correct-ah irukku.",
     "What you're saying seems correct."),
    ("Enakku indha situation pudikkala.",
     "I don't like this situation."),
    ("Innaiku mood seri illa.",
     "I'm not in a good mood today."),
    ("Naan konjam relax panna poren.",
     "I'm going to relax for a while."),
    ("Indha place romba amaidhiya irukku.",
     "This place is very peaceful."),
    ("Innum konjam practice panna improve aagum.",
     "With a little more practice, it will improve."),
]


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"File already exists: {OUTPUT}"
        )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT.open("w", encoding="utf-8") as file:
        for index, (user, meaning) in enumerate(CASES, 1):
            record = {
                "id": f"RIA-LF-EV-{index:03d}",
                "category": "everyday_vocabulary",
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

    print("\nRIA-1 EVERYDAY VOCABULARY")
    print("=" * 45)
    print("Draft records:", len(CASES))
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()

