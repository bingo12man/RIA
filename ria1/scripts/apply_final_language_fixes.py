
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ria1/data/language_foundation"

# Proposed corrections based on the eight audit warnings.
# Each correction must be explicitly confirmed by a human.

FIXES = {
    "RIA-LF-CS-006": {
        "tamil_equivalent":
            "தினமும் பதினைந்து நிமிஷம்தான் எனக்கு நேரம் இருக்கு.",
    },
    "RIA-LF-CS-007": {
        "tamil_equivalent":
            "சயின்ஸ் ஃபிக்ஷன் கதையா இருக்கணும், ஆனா ரொம்ப சிக்கலா வேண்டாம்.",
    },
    "RIA-LF-CS-011": {
        "tamil_equivalent":
            "ரேண்டம் ஃபாரஸ்ட்டையும் எக்ஸ்ஜிபூஸ்ட்டையும் ஒப்பிடணும். "
            "எனக்கு இன்ஃபரன்ஸ் ஸ்பீடுதான் முக்கியம்.",
        "ria_response":
            "Seri! Inference speed mukkiyam-na rendu model-um "
            "same dataset, hardware, batch size-la benchmark "
            "panni compare pannalaam. Tree count, depth, "
            "implementation poruthu speed maarum. "
            "Un use-case real-time prediction-ah?",
    },
    "RIA-LF-CS-012": {
        "tamil_equivalent":
            "மெலடி மெதுவா இருக்கணும், ஆனா கோரஸ் மட்டும் "
            "எனர்ஜெட்டிக்கா இருக்கணும்.",
    },
    "RIA-LF-CS-014": {
        "tamil_equivalent":
            "ரிட்ரீவல் பகுதியை மட்டும் கொஞ்சம் விரிவா சொல்லு.",
    },
    "RIA-LF-CS-016": {
        "tamil_equivalent":
            "அதே எரர்தான் வருது, ஆனா வேற லைன்ல.",
    },
    "RIA-LF-CS-020": {
        "tamil_equivalent":
            "கிராமரை மட்டும் சரி பண்ணு. ஸ்டைலை மாத்தாதே.",
    },
    "RIA-LF-EI-019": {
        "ria_response":
            "Awww, first day office-ah! Konjam tension "
            "irukkum dhaan, adhu normal. Relax-ah po, "
            "ellar kittayum friendly-ah pesu. "
            "Un first day nalla pogattum!",
    },
}


def get_review_path(record_id):
    if record_id.startswith("RIA-LF-CS-"):
        batch = "context_switching_001"
    elif record_id.startswith("RIA-LF-EI-"):
        batch = "emotion_intent_001"
    else:
        raise ValueError(f"Unknown batch: {record_id}")

    return DATA / f"{batch}_reviews.json"


def save_json(path, data):
    temp = path.with_suffix(".tmp")

    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    temp.replace(path)


def main():
    applied = 0
    skipped = 0

    print("\nRIA-1 LANGUAGE QUALITY CORRECTIONS")
    print("=" * 55)

    for record_id, corrections in FIXES.items():
        path = get_review_path(record_id)

        state = json.loads(
            path.read_text(encoding="utf-8")
        )

        review = state["reviews_by_id"].get(record_id)

        if not review or review.get("status") != "approved":
            raise ValueError(
                f"Approved review not found: {record_id}"
            )

        print("\n" + "=" * 55)
        print("RECORD:", record_id)

        for field, new_value in corrections.items():
            print(f"\nFIELD: {field}")
            print("CURRENT:", review.get(field))
            print("PROPOSED:", new_value)

        confirm = input(
            "\nApply these corrections? [y/N]: "
        ).strip().lower()

        if confirm != "y":
            skipped += 1
            print("Skipped.")
            continue

        backup = path.with_name(
            path.name + ".before_final_fixes.bak"
        )

        if not backup.exists():
            shutil.copy2(path, backup)

        for field, new_value in corrections.items():
            review[field] = new_value

        review["quality_corrected_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        save_json(path, state)

        applied += 1
        print("Correction saved.")

    print("\n" + "=" * 55)
    print("CORRECTION SUMMARY")
    print("Applied:", applied)
    print("Skipped:", skipped)
    print("Total proposed:", len(FIXES))
    print("Original source JSONL files unchanged.")


if __name__ == "__main__":
    main()

