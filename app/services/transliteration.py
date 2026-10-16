
import re

# Common conversational expressions.
PHRASE_MAP = {
    "எனக்கு": "enakku",
    "தமிழ்": "tamil",
    "தெரியும்": "theriyum",
    "நீங்க": "neenga",
    "எப்படி": "epdi",
    "இருக்கீங்க": "irukkeenga",
    "நான்": "naan",
    "நல்லா": "nalla",
    "இருக்கேன்": "irukken",
    "வேணும்": "venum",
    "கொஞ்சம்": "konjam",
    "ரொம்ப": "romba",
    "சரி": "seri",
    "ஆமா": "aama",
    "இல்ல": "illa",
    "சோர்வாக": "sorva",
    "இருக்கீங்களா": "irukkeengala",
    "வேலை": "velai",
    "மற்றும்": "matrum",
    "ப்ராஜெக்ட்ல": "project-la",
    "பேலன்ஸ்": "balance",
    "பண்றது": "panradhu",
    "கஷ்டமா": "kashtama",
    "இருக்குதா": "irukkudha",
    "ரெஸ்ட்": "rest",
    "எடுங்க": "edunga",
    "உங்களுக்கு": "ungalukku",
    "உதவி": "udhavi",
    "முடியும்": "mudiyum",

}

VOWELS = {
    "அ": "a", "ஆ": "aa",
    "இ": "i", "ஈ": "ee",
    "உ": "u", "ஊ": "oo",
    "எ": "e", "ஏ": "e",
    "ஐ": "ai", "ஒ": "o",
    "ஓ": "o", "ஔ": "au"
}

VOWEL_SIGNS = {
    "ா": "aa", "ி": "i",
    "ீ": "ee", "ு": "u",
    "ூ": "oo", "ெ": "e",
    "ே": "e", "ை": "ai",
    "ொ": "o", "ோ": "o",
    "ௌ": "au"
}

CONSONANTS = {
    "க": "k", "ங": "ng",
    "ச": "ch", "ஞ": "nj",
    "ட": "t", "ண": "n",
    "த": "th", "ந": "n",
    "ப": "p", "ம": "m",
    "ய": "y", "ர": "r",
    "ல": "l", "வ": "v",
    "ழ": "zh", "ள": "l",
    "ற": "r", "ன": "n",
    "ஜ": "j", "ஷ": "sh",
    "ஸ": "s", "ஹ": "h"
}

PULLI = "்"


def transliterate_word(word: str) -> str:
    if word in PHRASE_MAP:
        return PHRASE_MAP[word]

    result = []
    i = 0

    while i < len(word):
        char = word[i]

        if char in VOWELS:
            result.append(VOWELS[char])

        elif char in CONSONANTS:
            consonant = CONSONANTS[char]

            if i + 1 < len(word):
                next_char = word[i + 1]

                if next_char == PULLI:
                    result.append(consonant)
                    i += 2
                    continue

                if next_char in VOWEL_SIGNS:
                    result.append(
                        consonant + VOWEL_SIGNS[next_char]
                    )
                    i += 2
                    continue

            result.append(consonant + "a")

        else:
            result.append(char)

        i += 1

    return "".join(result)


def tamil_to_tanglish(text: str) -> str:
    tokens = re.findall(
        r"[\u0B80-\u0BFF]+|[^\u0B80-\u0BFF]+",
        text
    )

    result = []

    for token in tokens:
        if re.fullmatch(r"[\u0B80-\u0BFF]+", token):
            result.append(transliterate_word(token))
        else:
            result.append(token)

    return "".join(result)
