
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OUT = (
    ROOT / "ria1/data/language_foundation/"
    "negation_corrections_001.jsonl"
)

CASES = [
    ("Enakku tea vendaam, coffee podhum.",
     "I don't want tea; coffee is enough."),
    ("Naan andha file-ah delete pannala.",
     "I did not delete that file."),
    ("Innum payment varala.",
     "The payment hasn't arrived yet."),
    ("Idhu enoda laptop illa.",
     "This isn't my laptop."),
    ("Meeting cancel aagala, postpone aayiduchu.",
     "The meeting was postponed, not cancelled."),
    ("Naan kovama illa, konjam disappointed-ah irukken.",
     "I'm not angry; I'm a little disappointed."),
    ("Indha answer correct illa.",
     "This answer is incorrect."),
    ("Enakku full explanation vendaam, example podhum.",
     "I don't want a full explanation; an example is enough."),
    ("Indha app-ah naan install pannave illa.",
     "I never installed this application."),
    ("Nee sonna date correct illa, Friday dhaan.",
     "The date you mentioned is wrong; it's Friday."),
    ("Avan message pannala, direct-ah call pannaan.",
     "He didn't message; he called directly."),
    ("Enakku sugar illama coffee venum.",
     "I want coffee without sugar."),
    ("Indha problem hardware-la illa, software-la irukku.",
     "This problem is in the software, not the hardware."),
    ("Naan fail aagala, result innum varala.",
     "I haven't failed; the result hasn't come yet."),
    ("Nee explain pannadhu puriyala, vera example sollu.",
     "I didn't understand your explanation; give another example."),
    ("Adhu en question-ku answer illa.",
     "That doesn't answer my question."),
    ("Andha song-ah naan ezhudhinaen, paadala.",
     "I wrote that song; I didn't sing it."),
    ("Enakku reminder thevai illa.",
     "I don't need a reminder."),
    ("Naan dinner order pannala, veetla samaichen.",
     "I didn't order dinner; I cooked at home."),
    ("Nee rendu options sonna, aana enakku third option venum.",
     "You gave two options, but I want a third one."),
    ("Code run aagudhu, aana output correct illa.",
     "The code runs, but its output is incorrect."),
    ("Enakku andha topic ippo discuss panna viruppam illa.",
     "I don't want to discuss that topic now."),
    ("Naan unkitte translation kekkala, meaning ketten.",
     "I asked you for the meaning, not a translation."),
    ("Indha task mudinjiduchu nu sollala, almost mudinjiduchu.",
     "I didn't say the task was finished; it's almost finished."),
    ("Nee solra assumption thappu, naan beginner illa.",
     "Your assumption is wrong; I'm not a beginner."),
]


def main():
    if OUT.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing batch: {OUT}"
        )

    assert len(CASES) == 25

    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8") as file:
        for index, (prompt, meaning) in enumerate(CASES, 1):
            record = {
                "id": f"RIA-LF-NC-{index:03d}",
                "category": "negation_corrections",
                "language": "tanglish",
                "user_message": prompt,
                "english_meaning": meaning,
                "tamil_equivalent": "",
                "ria_response": "",
                "review_status": "draft",
                "source": "original_language_authoring",
            }
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    print("\nRIA-1 NEGATION AND CORRECTIONS")
    print("=" * 45)
    print("Draft records:", len(CASES))
    print("Approved: 0")
    print("Saved:", OUT)


if __name__ == "__main__":
    main()

