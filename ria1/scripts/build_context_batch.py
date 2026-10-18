
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ria1/data/language_foundation/context_switching_001.jsonl"

# Format:
# Previous user, previous Ria, new user, intended meaning

CASES = [
    (
        "Enakku recursion puriyala.",
        "Recursion-na oru function thannaye call pannuradhu.",
        "Adhuku oru simple Python example kaatu.",
        "The user wants a simple Python example of recursion."
    ),
    (
        "Naan oru love song ezhudhren.",
        "Super! Enna mood-la song venum?",
        "Konjam playful-ah irukkanum.",
        "The user wants the love song to have a playful mood."
    ),
    (
        "Naalaikku interview irukku.",
        "Enna role-ku interview?",
        "AI Engineer role. Technical questions first prepare pannalaam.",
        "The user wants to prepare technical questions for an AI Engineer interview."
    ),
    (
        "En code-la error varudhu.",
        "Error message share pannu.",
        "Idho traceback. Last line explain pannu.",
        "The user wants the last line of a Python traceback explained."
    ),
    (
        "Oru workout routine suggest pannu.",
        "Beginner routine venuma?",
        "Aama, aana equipment illama.",
        "The user wants a beginner workout routine without equipment."
    ),
    (
        "Enakku guitar learn pannanum.",
        "Basics-la start pannalaam.",
        "Daily 15 minutes dhaan irukku.",
        "The user only has fifteen minutes daily for guitar practice."
    ),
    (
        "Naan oru story idea think panren.",
        "Genre enna?",
        "Sci-fi, but romba complicated-ah vendaam.",
        "The user wants a science-fiction story that is not overly complicated."
    ),
    (
        "Enakku project architecture help venum.",
        "Backend details sollu.",
        "FastAPI use panren, database MongoDB.",
        "The user is providing FastAPI and MongoDB as the project's technologies."
    ),
    (
        "Indha paragraph romba formal-ah irukku.",
        "Casual-ah rewrite pannalaam.",
        "Aama, but meaning change aaga koodaadhu.",
        "The user wants a casual rewrite that preserves the original meaning."
    ),
    (
        "Oru email draft panni kudu.",
        "Yaarukku anuppanum?",
        "HR-ku. Polite-ah irukkanum, short-ah.",
        "The user wants a short, polite email to HR."
    ),
    (
        "Rendu models compare pannalaam.",
        "Endha models?",
        "Random Forest and XGBoost. Inference speed mukkiyam.",
        "The user wants a Random Forest versus XGBoost comparison focused on inference speed."
    ),
    (
        "En song-ku beat choose pannanum.",
        "Song tempo epdi irukku?",
        "Slow melody. Aana chorus energetic-ah venum.",
        "The user has a slow melody but wants an energetic chorus."
    ),
    (
        "Naan oru trip plan panren.",
        "Budget evlo?",
        "5k-kulla mudikkanum.",
        "The user wants to keep the trip budget within five thousand rupees."
    ),
    (
        "Enakku RAG explain pannu.",
        "RAG-na retrieval-augmented generation.",
        "Retrieval part mattum detail-ah sollu.",
        "The user wants only the retrieval component of RAG explained in detail."
    ),
    (
        "Oru recipe suggest pannu.",
        "Veg-ah non-veg-ah?",
        "Veg dhaan. Paneer irukku veetla.",
        "The user wants a vegetarian recipe using paneer."
    ),
    (
        "Indha solution work aagala.",
        "Enna problem vandhuchu?",
        "Same error dhaan, but different line-la.",
        "The previous solution did not work; the same error occurs on another line."
    ),
    (
        "Enakku oru presentation ready pannanum.",
        "Topic enna?",
        "Cybersecurity. Beginners-ku easy-ah puriyanum.",
        "The user wants a beginner-friendly cybersecurity presentation."
    ),
    (
        "Namma plan-la three steps irukku.",
        "Seri, first step-la start pannalaam.",
        "Second step-ku direct-ah pogalaama?",
        "The user asks whether they can skip ahead to the second step."
    ),
    (
        "En laptop romba slow-ah irukku.",
        "Recent-ah edhaavadhu install pannuniya?",
        "Illa, update-ku apram dhaan ipdi.",
        "The user says the laptop became slow after an update, not an installation."
    ),
    (
        "Naan oru poem ezhudhirukken.",
        "Share pannu, paakalam.",
        "Grammar mattum correct pannu. Style change pannaadha.",
        "The user wants grammar corrections only, without changing the poem's style."
    ),
    (
        "Indha concept enakku puriyudhu.",
        "Super, next concept pogalaam.",
        "Wait, adhula oru doubt irukku.",
        "The user has another question about the current concept and wants to pause."
    ),
    (
        "Enakku time management help venum.",
        "Tasks-ah priority order-la arrange pannalaam.",
        "First urgent ones mattum list pannu.",
        "The user wants only urgent tasks listed first."
    ),
    (
        "Naan oru photo edit pannanum.",
        "Enna change venum?",
        "Background mattum remove pannu, face touch pannaadha.",
        "The user wants the photo background removed without modifying the face."
    ),
    (
        "Enakku English-la answer kudu.",
        "Sure, I'll reply in English.",
        "Actually Tanglish-la pesu, natural-ah.",
        "The user changes their preference and now wants natural Tanglish."
    ),
    (
        "Oru learning roadmap create pannalaam.",
        "Enna subject-ku?",
        "Deep learning. First fundamentals, apram projects.",
        "The user wants a deep-learning roadmap starting with fundamentals and progressing to projects."
    ),
]


def main():
    if OUT.exists():
        raise FileExistsError(f"Batch already exists: {OUT}")

    assert len(CASES) == 25
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8") as file:
        for index, (previous_user, previous_ria, user, meaning) in enumerate(CASES, 1):
            row = {
                "id": f"RIA-LF-CS-{index:03d}",
                "category": "context_switching",
                "language": "tanglish",
                "previous_user": previous_user,
                "previous_ria": previous_ria,
                "user_message": user,
                "english_meaning": meaning,
                "tamil_equivalent": "",
                "ria_response": "",
                "review_status": "draft",
                "source": "original_context_authoring",
            }
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("\nRIA-1 CONTEXT & CODE-SWITCHING")
    print("=" * 45)
    print("Draft conversations:", len(CASES))
    print("Status: Awaiting human review")
    print("Saved:", OUT)


if __name__ == "__main__":
    main()

