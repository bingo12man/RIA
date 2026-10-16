
import re
from typing import Literal

Language = Literal["english", "tamil", "tanglish"]

TANGLISH_WORDS = {
    "enna", "ennaku", "enakku", "nee",
    "naan", "namma", "unakku", "irukku",
    "irukka", "theriyuma", "sollu",
    "sollunga", "pannu", "panren",
    "epdi", "eppadi", "iniku", "innikku",
    "venum", "illa", "aama", "seri",
    "romba", "konjam", "pesalama",
    "puriyala", "kudu", "kudunga"
}

LANGUAGE_RULES = {
    "english": """
Respond in natural English.
Use a warm, thoughtful and clear conversational style.
""",
    "tamil": """
Respond primarily in natural spoken Tamil,
using Tamil script.
Keep your response simple and meaningful.
Do not invent Tamil words.
""",
    "tanglish": """
Respond in conversational Tamil written in English letters.

Use natural spoken Tamil grammar.
English technical words are allowed where useful.
Do not switch entirely to English.
Do not use Tamil script.
Do not invent Tamil-sounding nonsense.
Keep your answer clear, meaningful and friendly.
"""
}


def detect_language(text: str) -> Language:
    # Detect Tamil Unicode characters.
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "tamil"

    # Split Roman-script text into words.
    words = set(
        re.findall(r"[a-zA-Z]+", text.lower())
    )

    matches = words.intersection(TANGLISH_WORDS)

    if len(matches) >= 2:
        return "tanglish"

    return "english"


def get_language_instruction(language: Language) -> str:
    return LANGUAGE_RULES[language]


def validate_response(
    response: str,
    language: Language
) -> bool:
    if not response.strip():
        return False

    if language == "tanglish":
        # Check only that Tamil script is absent.
        return not bool(
            re.search(r"[\u0B80-\u0BFF]", response)
        )

    return True
