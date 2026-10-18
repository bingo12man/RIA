
import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "ria1/data/evaluation"
OUTPUT = EVAL / "generalization_v2"

RELEASE = (
    ROOT / "ria1/data/releases/language_foundation_v1/"
    "meaning_reference.jsonl"
)

BENCHMARK = EVAL / "tanglish_comprehension_v1.jsonl"

# New candidate examples.
# Expected meanings are for human verification,
# never for model prompting or retrieval.

SINGLE = [
    # Negation and intent
    ("Indha parcel-a open panna koodaadhu.",
     "Don't open this parcel.", "negation"),
    ("Enakku ippo saapida ishtam illa.",
     "I don't feel like eating right now.", "negation"),
    ("Andha photo-va share pannidaadha.",
     "Don't share that photo.", "negation"),
    ("Innum payment varave illa.",
     "The payment still hasn't arrived.", "negation"),

    # Tense and timing
    ("Nethu night current poiduchu.",
     "The electricity went out last night.", "tense"),
    ("Adutha vaaram oorukku kelamburen.",
     "I'm leaving for my hometown next week.", "tense"),
    ("Naan vandhadhukulla avanga kelambittaanga.",
     "They had left by the time I arrived.", "tense"),
    ("Meeting mudinju apram pesalaam.",
     "Let's talk after the meeting ends.", "tense"),

    # Pronouns and relationships
    ("Ava sonnadha avankitta sollaadha.",
     "Don't tell him what she said.", "pronouns"),
    ("Avangalukku naan already message anuppitten.",
     "I've already sent them a message.", "pronouns"),
    ("En thambi innikki late-ah varuvaan.",
     "My younger brother will come late today.", "pronouns"),
    ("Nee kudutha book-a naan padichitten.",
     "I've finished reading the book you gave me.", "pronouns"),

    # Questions and uncertainty
    ("Idhukku vera vazhi irukka?",
     "Is there another way to do this?", "questions"),
    ("Eppo thirumbi varuveenga?",
     "When will you return?", "questions"),
    ("Indha issue yen thirumba varudhu?",
     "Why does this issue keep happening?", "questions"),
    ("Nee confirm pannitiya illaya?",
     "Have you confirmed it or not?", "questions"),

    # Emotions and preferences
    ("Enakku romba emaatram-a irukku.",
     "I'm feeling very disappointed.", "emotion"),
    ("Konjam thaniya irukkanum pola irukku.",
     "I feel like being alone for a while.", "emotion"),
    ("Indha paattu kekkumbodhu sandhoshama irukku.",
     "Listening to this song makes me happy.", "emotion"),
    ("Yaarayum disturb panna virumbala.",
     "I don't want to disturb anyone.", "emotion"),

    # Code switching
    ("API response slow-ah irukku, logs check pannu.",
     "The API response is slow; check the logs.", "code_switch"),
    ("Deployment panna munnaadi backup eduthuko.",
     "Take a backup before deploying.", "code_switch"),
    ("Indha branch-a merge panna ready-ah irukka?",
     "Are you ready to merge this branch?", "code_switch"),
    ("Camera feed freeze aagudhu, restart panni paaru.",
     "The camera feed is freezing; try restarting it.",
     "code_switch"),

    # Colloquial spelling variations
    ("Enaku adhu seriya purila.",
     "I didn't understand that properly.", "variation"),
    ("Iniki seekiram thoonganum.",
     "I need to sleep early today.", "variation"),
    ("Neenga engayo paatha madhiri iruku.",
     "You seem familiar, as though I've seen you somewhere.",
     "variation"),
    ("Adha marubadiyum sollunga.",
     "Please say that again.", "variation"),

    # Quantity, conditions and requests
    ("Rendu perukku mattum ticket book pannu.",
     "Book tickets for only two people.", "intent"),
    ("Mazhai penja veliya poga vendaam.",
     "Don't go outside if it rains.", "intent"),
    ("Oru mani neram kazhichu nyabagam paduthu.",
     "Remind me after one hour.", "intent"),
    ("Adhula paadhi mattum use pannu.",
     "Use only half of it.", "intent"),
]

# Context is essential to determining the meaning.
CONTEXT = [
    {
        "previous_user": "Naan rendu laptops compare panren.",
        "previous_ria": "Battery life mukkiyama, performance mukkiyama?",
        "user_message": "Battery dhaan first priority.",
        "expected": "Battery life is the user's first priority.",
    },
    {
        "previous_user": "Naan oru presentation prepare panren.",
        "previous_ria": "Evlo slides venum?",
        "user_message": "Maximum aaru slides podhum.",
        "expected": "The user wants no more than six slides.",
    },
    {
        "previous_user": "Inniku evening movie polaama?",
        "previous_ria": "Comedy movie paakalaama?",
        "user_message": "Illa, thriller better.",
        "expected": "The user prefers a thriller instead of a comedy.",
    },
    {
        "previous_user": "Enakku rendu interviews schedule aayirukku.",
        "previous_ria": "Edhukku first prepare pannalaam?",
        "user_message": "Friday irukkuradhukku first.",
        "expected": "The user wants to prepare first for the interview on Friday.",
    },
    {
        "previous_user": "Naan oru song write panren.",
        "previous_ria": "Lyrics change panlama, tune change panlama?",
        "user_message": "Tune mattum maathalaam.",
        "expected": "The user wants to change only the tune, not the lyrics.",
    },
    {
        "previous_user": "Indha file-a share pannava?",
        "previous_ria": "Team full-ah anuppava?",
        "user_message": "Manager-ku mattum anuppu.",
        "expected": "The user wants the file sent only to the manager.",
    },
    {
        "previous_user": "Naalaikku morning run pogalaamnu irukken.",
        "previous_ria": "Five kilometres try pannalama?",
        "user_message": "Illa, moonu pothum.",
        "expected": "The user wants to run three kilometres instead of five.",
    },
    {
        "previous_user": "Project-ku Python illa Java use pannalama?",
        "previous_ria": "Ungalukku endha language comfortable?",
        "user_message": "Rendume okay, aana first one easy.",
        "expected": "The user is comfortable with both but finds Python easier.",
    },
]


def normalize(text):
    return " ".join(
        re.findall(r"\w+", text.casefold())
    )


def read_jsonl(path):
    if not path.exists():
        return []

    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def existing_prompts():
    prompts = []

    for record in read_jsonl(RELEASE):
        if record.get("tanglish"):
            prompts.append({
                "source": "training_release",
                "text": record["tanglish"],
            })

    for record in read_jsonl(BENCHMARK):
        if record.get("user_message"):
            prompts.append({
                "source": "held_out_benchmark",
                "text": record["user_message"],
            })

    # Previously used development test inputs.
    prior_files = [
        EVAL / "grammar_generalization_v1.json",
        EVAL / "tamil_script_diagnostic_v1.json",
        EVAL / "gemma_transliteration_v1.json",
        EVAL / "indicxlit_unseen_pipeline_v1.json",
        EVAL / "direct_vs_converted_comparison_v1.json",
    ]

    for path in prior_files:
        if not path.exists():
            continue

        payload = json.loads(
            path.read_text(encoding="utf-8")
        )

        rows = (
            payload if isinstance(payload, list)
            else payload.get("tests", [])
        )

        for record in rows:
            text = (
                record.get("tanglish")
                or record.get("original")
                or record.get("input")
            )

            if text:
                prompts.append({
                    "source": path.name,
                    "text": text,
                })

    return prompts


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            f"Candidate set already exists: {OUTPUT}"
        )

    rows = []

    for index, (text, meaning, category) in enumerate(
        SINGLE, 1
    ):
        rows.append({
            "id": f"RIA-GEN2-{index:03d}",
            "category": category,
            "user_message": text,
            "previous_user": None,
            "previous_ria": None,
            "expected_english": meaning,
            "human_review": "pending",
        })

    for index, item in enumerate(CONTEXT, len(SINGLE) + 1):
        rows.append({
            "id": f"RIA-GEN2-{index:03d}",
            "category": "context",
            "human_review": "pending",
            **item,
            "expected_english": item["expected"],
        })
        rows[-1].pop("expected")

    assert len(rows) == 40
    assert len({r["id"] for r in rows}) == 40

    prior = existing_prompts()
    warnings = []

    for row in rows:
        query = normalize(row["user_message"])

        for item in prior:
            previous = normalize(item["text"])

            similarity = SequenceMatcher(
                None, query, previous
            ).ratio()

            if similarity >= 0.78:
                warnings.append({
                    "id": row["id"],
                    "source": item["source"],
                    "similarity": round(similarity, 3),
                    "candidate": row["user_message"],
                    "existing": item["text"],
                })

    OUTPUT.mkdir(parents=True, exist_ok=False)

    # Store prompts separately from answer keys.
    prompts_path = OUTPUT / "prompts.jsonl"
    keys_path = OUTPUT / "answer_key.jsonl"

    with prompts_path.open("w", encoding="utf-8") as f:
        for row in rows:
            visible = {
                k: row[k]
                for k in (
                    "id", "category", "user_message",
                    "previous_user", "previous_ria",
                )
            }

            f.write(
                json.dumps(visible, ensure_ascii=False)
                + "\n"
            )

    with keys_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps({
                    "id": row["id"],
                    "expected_english": row["expected_english"],
                    "human_review": "pending",
                }, ensure_ascii=False) + "\n"
            )

    report = {
        "total": len(rows),
        "single_turn": len(SINGLE),
        "context": len(CONTEXT),
        "categories": dict(Counter(
            row["category"] for row in rows
        )),
        "overlap_warnings": warnings,
        "prompt_sha256": hash_file(prompts_path),
        "answer_key_sha256": hash_file(keys_path),
        "status": "candidate_not_yet_frozen",
        "limitations": [
            "Human review is still required.",
            "Similarity screening is lexical, not semantic.",
            "Dataset was authored after observing model failures.",
            "It is a development evaluation set, not an independent blind benchmark.",
            "Do not use these prompts or answers for training or retrieval.",
        ],
    }

    (OUTPUT / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print("\nRIA-1 GENERALIZATION EVALUATION V2")
    print("=" * 55)
    print("Total:", len(rows))
    print("Single-turn:", len(SINGLE))
    print("Context:", len(CONTEXT))
    print("Overlap warnings:", len(warnings))

    for warning in warnings[:10]:
        print(
            warning["id"],
            warning["source"],
            warning["similarity"],
            warning["candidate"],
        )

    print("Output:", OUTPUT)
    print("Status: Awaiting human review")


if __name__ == "__main__":
    main()

