
import re
from typing import Literal


Language = Literal["english", "tamil", "tanglish"]

TAMIL_SCRIPT = re.compile(r"[\u0B80-\u0BFF]")
ROMAN_WORDS = re.compile(r"[a-z]+")

TANGLISH_WORDS = {
    "aama", "aachu", "adhu", "aiyo",
    "anga", "appo", "approm", "avanga",
    "dhaan", "enna", "ennaku", "enakku",
    "ennoda", "epdi", "eppadi", "enga",
    "illa", "illai", "inga", "iniku",
    "innaiku", "innikku", "iruka",
    "irukku", "irukka", "kekkuren",
    "konjam", "kudunga", "kudu",
    "machan", "manasu", "naan",
    "namma", "nee", "neenga", "nalla",
    "pannalaam", "pannum", "pannu",
    "panren", "pesalama", "pesalaam",
    "poga", "pochu", "puriyala",
    "romba", "sari", "seri", "sollu",
    "sollunga", "solren", "semma",
    "thaan", "theriyuma", "theriyum",
    "theriyala", "unga", "unakku",
    "venum", "vandha", "yaaru",
}

LANGUAGE_RULES = {
    "english": (
        "Respond in natural conversational English. "
        "Be warm, clear and friendly. "
        "Do not use Tamil script or Romanized Tamil."
    ),
    "tamil": (
        "Respond in natural spoken Tamil using Tamil script. "
        "Avoid overly literary Tamil. "
        "English technical words are acceptable when useful."
    ),
    "tanglish": (
        "Respond in naturally spoken Tamil written using "
        "English letters. English words may be mixed in "
        "where they sound natural. "
        "Use real Tamil sentence structure, not translated "
        "English grammar. Avoid invented Tamil-sounding words. "
        "Do not use Tamil script."
    ),
}


def detect_language(text: str) -> Language:
    if TAMIL_SCRIPT.search(text):
        return "tamil"

    words = set(ROMAN_WORDS.findall(text.casefold()))
    matches = words & TANGLISH_WORDS

    if len(matches) >= 2:
        return "tanglish"

    return "english"


def get_language_instruction(language: Language) -> str:
    return LANGUAGE_RULES[language]


def validate_response(
    response: str,
    language: Language
) -> bool:
    """
    Check basic language-script compatibility.

    This does not measure grammar, naturalness,
    emotional quality, relevance or factual accuracy.
    """
    if not isinstance(response, str) or not response.strip():
        return False

    has_tamil_script = bool(TAMIL_SCRIPT.search(response))

    if language == "tamil":
        return has_tamil_script

    if language in ("english", "tanglish"):
        return not has_tamil_script

    return False
