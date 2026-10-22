
import asyncio
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import edge_tts
import numpy as np
import soundfile as sf

from voice.text_processing import clean_for_speech


TTS_ENGINE = os.getenv("RIA_TTS_ENGINE", "edge")

ENGLISH_VOICE = os.getenv(
    "RIA_ENGLISH_VOICE", "en-IN-NeerjaNeural"
)

TAMIL_VOICE = os.getenv(
    "RIA_TAMIL_VOICE", "ta-IN-PallaviNeural"
)

MAC_VOICE = os.getenv("RIA_MAC_VOICE", "Samantha")
SPEECH_RATE = os.getenv("RIA_TTS_RATE", "+0%")

OUTPUT_SAMPLE_RATE = 24000


def prepare_text(text):
    text = re.sub(
        r"^\s*(?:RIA|Ria|Assistant)\s*:\s*",
        "",
        text.strip(),
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\bRIA\b",
        "Ria",
        text,
        flags=re.IGNORECASE
    )

    # Remove decorative emoji before speech synthesis.
    # Keep ordinary letters, accents, punctuation and numbers.
    text = "".join(
        char for char in text
        if not (
            unicodedata.category(char) == "So"
            or char in ("\\u200d", "\\ufe0f", "\\u20e3")
            or 0x1F3FB <= ord(char) <= 0x1F3FF
        )
    )

    return clean_for_speech(text)


def choose_voice(language):
    if language == "tamil":
        return TAMIL_VOICE

    # Tanglish is temporarily synthesized with
    # the English voice until multilingual TTS improves.
    return ENGLISH_VOICE


async def generate_edge_audio(text, language, path):
    communicator = edge_tts.Communicate(
        text=text,
        voice=choose_voice(language),
        rate=SPEECH_RATE
    )

    await communicator.save(str(path))


def decode_audio(source, output):
    """
    Decode audio into 24 kHz mono PCM WAV.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", str(source),
            "-ar", str(OUTPUT_SAMPLE_RATE),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(output)
        ],
        check=True,
        capture_output=True,
        timeout=30
    )

    audio, sample_rate = sf.read(
        str(output),
        dtype="float32",
        always_2d=False
    )

    if sample_rate != OUTPUT_SAMPLE_RATE:
        raise ValueError("Unexpected audio sample rate")

    return np.asarray(audio, dtype=np.float32).flatten()


def generate_macos_pcm(text, directory):
    source = Path(directory) / "speech.aiff"
    output = Path(directory) / "speech.wav"

    subprocess.run(
        [
            "say",
            "-v", MAC_VOICE,
            "-r", "165",
            "-o", str(source),
            text
        ],
        check=True,
        capture_output=True,
        timeout=60
    )

    return decode_audio(source, output)


def synthesize_to_pcm(text, language="english"):
    """
    Generate a sentence as PCM samples.

    This function does not play audio.
    It can run in a background worker.

    Returns a float32 NumPy array.
    """
    cleaned = prepare_text(text)

    if not cleaned:
        return np.empty(0, dtype=np.float32)

    with tempfile.TemporaryDirectory() as directory:

        if TTS_ENGINE == "macos":
            return generate_macos_pcm(
                cleaned,
                directory
            )

        mp3_path = Path(directory) / "speech.mp3"
        wav_path = Path(directory) / "speech.wav"

        try:
            asyncio.run(
                generate_edge_audio(
                    cleaned,
                    language,
                    mp3_path
                )
            )

            return decode_audio(
                mp3_path,
                wav_path
            )

        except Exception as exc:
            print(f"[TTS] Neural voice failed: {exc}")
            print("[TTS] Trying macOS fallback.")

            return generate_macos_pcm(
                cleaned,
                directory
            )
