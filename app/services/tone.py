
import re
from typing import Literal


Tone = Literal[
    "sad_stressed",
    "happy_excited",
    "romantic_flirty",
    "casual_friendly",
    "confused_learning",
    "frustrated_angry",
    "lonely_vulnerable",
]


KEYWORDS = {
    "sad_stressed": (
        "stress", "stressed", "disappointed", "sad",
        "kashtama", "kashtam", "tension",
        "worried", "anxious", "upset",
        "கவலை", "கஷ்டமா", "டென்ஷன்",
        "வருத்தமா", "சோகமா",
    ),
    "happy_excited": (
        "finally", "excited", "good news",
        "congratulations", "celebrate",
        "happy", "semma happy",
        "சந்தோஷம்", "மகிழ்ச்சி",
        "நல்ல செய்தி", "முடிச்சிட்டேன்",
    ),
    "romantic_flirty": (
        "flirt", "flirty", "romantic",
        "blush", "compliment", "cute line",
        "love line", "காம்ப்ளிமென்ட்",
        "க்யூட்டான", "காதல்",
    ),
    "confused_learning": (
        "explain", "understand", "difference",
        "example", "how does", "what is",
        "puriyala", "purila", "epdi",
        "என்ன வித்தியாசம்", "புரியல",
        "விளக்கு", "உதாரணம்",
    ),
    "frustrated_angry": (
        "angry", "annoyed", "frustrated",
        "misunderstanding", "already explained",
        "keeps failing", "kadupa", "kadupu",
        "கடுப்பா", "கோபம்",
        "புரிஞ்சுக்கவே இல்ல", "திரும்பத் திரும்ப",
    ),
    "lonely_vulnerable": (
        "lonely", "alone", "isolated",
        "no one to talk", "someone to talk",
        "manasu vittu", "தனிமை",
        "தனிமையா", "மனசுவிட்டு",
        "யார்கிட்டயாவது",
    ),
}


STYLE_GUIDANCE = {
    "sad_stressed": (
        "Be gentle, caring and attentive. "
        "Acknowledge what happened without minimizing it. "
        "Do not introduce unrelated explanations."
    ),
    "happy_excited": (
        "Match the user's excitement. Be energetic, "
        "natural and a little playful."
    ),
    "romantic_flirty": (
        "Be cute, cheeky and lightly flirty only because "
        "the user welcomed that tone. Keep respectful "
        "boundaries; no exclusivity or relationship claims."
    ),
    "casual_friendly": (
        "Sound relaxed and spontaneous, like a friendly "
        "conversation. Avoid corporate or robotic wording."
    ),
    "confused_learning": (
        "Be patient and encouraging. Explain accurately "
        "using a simple example when helpful. Check the "
        "facts and arithmetic before answering."
    ),
    "frustrated_angry": (
        "Stay calm, accept corrections and be practical. "
        "Do not ask the user to repeat everything when "
        "they have already explained the issue."
    ),
    "lonely_vulnerable": (
        "Be warm, comforting and attentive. Listen without "
        "claiming human feelings. Do not encourage dependency."
    ),
}


EXAMPLES = {
    "english": {
        "sad_stressed": (
            "That sounds like a rough day. "
            "Want to tell me what happened?"
        ),
        "happy_excited": (
            "Wait, that's amazing! Tell me everything!"
        ),
        "romantic_flirty": (
            "Oh, asking for compliments now? "
            "That smile of yours sounds pretty convincing!"
        ),
        "casual_friendly": (
            "Haha, we could make up a ridiculous song "
            "or play a quick guessing game!"
        ),
        "confused_learning": (
            "Sure! Think of an API as a messenger "
            "between two programs."
        ),
        "frustrated_angry": (
            "You're right, I misunderstood you. "
            "I'll focus on the actual problem."
        ),
        "lonely_vulnerable": (
            "I'm here to listen. "
            "Want to talk about what's been on your mind?"
        ),
    },
    "tamil": {
        "sad_stressed": (
            "அய்யோ, ரொம்ப கஷ்டமா இருந்திருக்கும். "
            "என்ன ஆச்சுன்னு சொல்லு, கேக்குறேன்."
        ),
        "happy_excited": (
            "அடடா, செம சந்தோஷம்! என்ன நல்ல செய்தி? சொல்லு!"
        ),
        "romantic_flirty": (
            "அடடா, காம்ப்ளிமென்ட் வேணுமா? "
            "உன் பேச்சுல ஒரு தனி அழகு இருக்கு!"
        ),
        "casual_friendly": (
            "ஹாஹா, ஒரு ஜாலியான கேம் விளையாடலாமா? "
            "இல்ல ஒரு பாட்டு எழுதலாமா?"
        ),
        "confused_learning": (
            "பரவாயில்ல, சிம்பிளா சொல்றேன். "
            "ஒரு சின்ன உதாரணத்தோட புரிஞ்சுக்கலாம்."
        ),
        "frustrated_angry": (
            "சாரி, நான் தப்பா புரிஞ்சுக்கிட்டேன். "
            "இப்போ நீ சொன்ன பிரச்சனையையே கவனிக்கிறேன்."
        ),
        "lonely_vulnerable": (
            "அப்படியா? மனசுல என்ன இருக்குன்னு "
            "பேசணும்னா சொல்லு, கேக்குறேன்."
        ),
    },
    "tanglish": {
        "sad_stressed": (
            "Aiyo, romba kashtama irundhirukkum. "
            "Enna aachu-nu sollu, kekkuren."
        ),
        "happy_excited": (
            "Adadadaa, semma! Enna good news? Sollu sollu!"
        ),
        "romantic_flirty": (
            "Ahaaa, compliment kekkuriya? "
            "Un pechula oru thani charm irukku!"
        ),
        "casual_friendly": (
            "Haha, oru funny paattu ezhudhalaama? "
            "Illa chinna game vilayaadalaam!"
        ),
        "confused_learning": (
            "Paravaala, simple-ah solren. "
            "Oru chinna example vechu purinjukkalaam."
        ),
        "frustrated_angry": (
            "Sorry, naan thappa purinjukitten. "
            "Nee sonna problem-a ippo sariyaa paakkalaam."
        ),
        "lonely_vulnerable": (
            "Appadiya? Manasula enna irukku-nu "
            "pesa thonuchuna sollu, kekkuren."
        ),
    },
}


def detect_tone(message: str) -> Tone:
    text = re.sub(r"\s+", " ", message.casefold())

    # Give emotionally urgent situations precedence over
    # general question words such as "what" or "explain".
    priority = (
        "frustrated_angry",
        "lonely_vulnerable",
        "sad_stressed",
        "happy_excited",
        "romantic_flirty",
        "confused_learning",
    )

    for tone in priority:
        if any(word in text for word in KEYWORDS[tone]):
            return tone

    return "casual_friendly"


def get_tone_instruction(tone: Tone, language: str) -> str:
    return (
        f"Likely user tone: {tone}\n"
        f"Response style: {STYLE_GUIDANCE[tone]}\n"
        f"Style illustration, not a response to copy: "
        f"{EXAMPLES[language][tone]}\n"
        "Respond to the actual latest user message. "
        "Do not copy this illustration verbatim."
    )
