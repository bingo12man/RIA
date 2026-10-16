
import asyncio
import os
import re
import subprocess
import tempfile
from pathlib import Path

import edge_tts


TTS_ENGINE = os.getenv("RIA_TTS_ENGINE", "edge")

ENGLISH_VOICE = os.getenv(
    "RIA_ENGLISH_VOICE",
    "en-US-JennyNeural"
)

TAMIL_VOICE = os.getenv(
    "RIA_TAMIL_VOICE",
    "ta-IN-PallaviNeural"
)

SPEECH_RATE = os.getenv(
    "RIA_TTS_RATE",
    "-10%"
)

MAC_VOICE = os.getenv(
    "RIA_MAC_VOICE",
    "Samantha"
)


def prepare_text(text):
    """Fix Ria's name pronunciation."""
    return re.sub(
        r"\bRIA\b",
        "Ria",
        text,
        flags=re.IGNORECASE
    )


def choose_voice(language):
    """Choose a female-sounding voice by language."""
    if language == "tamil":
        return TAMIL_VOICE

    # Tanglish currently uses English TTS.
    # We will improve this separately.
    return ENGLISH_VOICE


async def speak_edge(text, language):
    """Generate neural speech and play it on macOS."""
    voice = choose_voice(language)

    with tempfile.TemporaryDirectory() as directory:
        audio_path = Path(directory) / "ria_speech.mp3"

        communicator = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=SPEECH_RATE
        )

        await communicator.save(str(audio_path))

        subprocess.run(
            ["afplay", str(audio_path)],
            check=True
        )


def speak_macos(text):
    """Offline fallback using macOS speech."""
    subprocess.run(
        [
            "say",
            "-v",
            MAC_VOICE,
            "-r",
            "155",
            text
        ],
        check=True
    )


def speak(text, language="english"):
    """Speak a response with the selected TTS engine."""
    if not text or not text.strip():
        return

    text = prepare_text(text)

    if TTS_ENGINE == "macos":
        speak_macos(text)
        return

    try:
        asyncio.run(
            speak_edge(text, language)
        )

    except (
        Exception
    ) as exc:
        print(f"Neural TTS unavailable: {exc}")
        print("Using macOS speech fallback.")

        speak_macos(text)


if __name__ == "__main__":
    speak(
        "Hi! I'm Ria, your personal AI companion.",
        "english"
    )
