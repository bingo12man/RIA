
import asyncio
import os
import re
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import edge_tts
import numpy as np
import sounddevice as sd


TTS_ENGINE = os.getenv("RIA_TTS_ENGINE", "edge")

ENGLISH_VOICE = os.getenv(
    "RIA_ENGLISH_VOICE", "en-US-JennyNeural"
)
TAMIL_VOICE = os.getenv(
    "RIA_TAMIL_VOICE", "ta-IN-PallaviNeural"
)

SPEECH_RATE = os.getenv("RIA_TTS_RATE", "-10%")
MAC_VOICE = os.getenv("RIA_MAC_VOICE", "Samantha")

VOICE_INTERRUPT = (
    os.getenv("RIA_VOICE_INTERRUPT", "1") == "1"
)

SAMPLE_RATE = 16000
FRAME_SIZE = 480
MIN_INTERRUPT_LEVEL = 0.025
INTERRUPT_FRAMES = 6


TANGLISH_WORDS = {
    "vanakkam": "வணக்கம்",
    "naan": "நான்",
    "nee": "நீ",
    "neenga": "நீங்க",
    "unga": "உங்க",
    "ungalukku": "உங்களுக்கு",
    "unakku": "உனக்கு",
    "enakku": "எனக்கு",
    "ennoda": "என்னோட",
    "enna": "என்ன",
    "epdi": "எப்படி",
    "eppadi": "எப்படி",
    "irukka": "இருக்க",
    "irukku": "இருக்கு",
    "irukken": "இருக்கேன்",
    "irukkeenga": "இருக்கீங்க",
    "nalla": "நல்லா",
    "romba": "ரொம்ப",
    "konjam": "கொஞ்சம்",
    "seri": "சரி",
    "sari": "சரி",
    "aama": "ஆமா",
    "illa": "இல்ல",
    "illai": "இல்லை",
    "venum": "வேணும்",
    "vendam": "வேண்டாம்",
    "mudiyum": "முடியும்",
    "mudiyala": "முடியல",
    "pannalam": "பண்ணலாம்",
    "pannu": "பண்ணு",
    "pannunga": "பண்ணுங்க",
    "panradhu": "பண்றது",
    "sollu": "சொல்லு",
    "sollunga": "சொல்லுங்க",
    "pesu": "பேசு",
    "pesalam": "பேசலாம்",
    "kelu": "கேளு",
    "kudu": "குடு",
    "kudunga": "குடுங்க",
    "edunga": "எடுங்க",
    "eduthuko": "எடுத்துக்கோ",
    "innikku": "இன்னிக்கு",
    "inniku": "இன்னிக்கு",
    "naalaikku": "நாளைக்கு",
    "ippo": "இப்போ",
    "aprom": "அப்புறம்",
    "thaan": "தான்",
    "dhaan": "தான்",
    "kandippa": "கண்டிப்பா",
    "super": "சூப்பர்",
    "semma": "செம்ம",
    "kashtama": "கஷ்டமா",
    "sorva": "சோர்வா",
    "velai": "வேலை",
    "matrum": "மற்றும்",
    "nandri": "நன்றி",
    "puriyudhu": "புரியுது",
    "puriyala": "புரியல",
}


def prepare_text(text):
    return re.sub(
        r"\bRIA\b",
        "Ria",
        text,
        flags=re.IGNORECASE
    )


def choose_voice(language):
    if language == "tamil":
        return TAMIL_VOICE
    return ENGLISH_VOICE


def split_tanglish(text):
    tokens = re.findall(
        r"[\w]+|[^\w]+",
        text,
        flags=re.UNICODE
    )

    segments = []
    current_language = None
    current_text = ""

    for token in tokens:
        if not token:
            continue

        if not any(ch.isalnum() for ch in token):
            current_text += token
            continue

        normalized = token.lower()

        if re.search(r"[\u0B80-\u0BFF]", token):
            language = "tamil"
            spoken = token
        elif normalized in TANGLISH_WORDS:
            language = "tamil"
            spoken = TANGLISH_WORDS[normalized]
        else:
            language = "english"
            spoken = token

        if (
            current_language is not None
            and current_language != language
        ):
            if current_text.strip():
                segments.append(
                    (current_language, current_text.strip())
                )
            current_text = ""

        current_language = language
        current_text += spoken

    if current_text.strip():
        segments.append(
            (current_language or "english", current_text.strip())
        )

    return segments


def audio_level(frame):
    data = np.asarray(frame, dtype=np.float32)

    if data.size == 0:
        return 0.0

    return float(np.sqrt(np.mean(data ** 2)))


def stop_process(process):
    if process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def keyboard_interrupted():
    if not sys.stdin.isatty():
        return False

    ready, _, _ = select.select(
        [sys.stdin], [], [], 0
    )

    if ready:
        sys.stdin.readline()
        return True

    return False


def play_interruptible(command):
    """
    Play speech while monitoring the microphone.

    Returns True if playback was interrupted.
    Returns False if it finished normally.
    """

    stream = None
    threshold = MIN_INTERRUPT_LEVEL

    if VOICE_INTERRUPT:
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=FRAME_SIZE
            )
            stream.start()

            # Calibrate before starting playback.
            noise_samples = []

            for _ in range(10):
                frame, _ = stream.read(FRAME_SIZE)
                noise_samples.append(audio_level(frame))

            threshold = max(
                MIN_INTERRUPT_LEVEL,
                float(np.mean(noise_samples)) * 4
            )

        except (sd.PortAudioError, OSError) as exc:
            print(f"Mic interruption unavailable: {exc}")

            if stream is not None:
                stream.close()
                stream = None

    process = None

    try:
        process = subprocess.Popen(command)

        print(
            "🔊 Ria is speaking. "
            "Speak or press ENTER to interrupt."
        )

        active_frames = 0

        while process.poll() is None:
            if keyboard_interrupted():
                stop_process(process)
                print("⏹️ Keyboard interruption.")
                return True

            if stream is not None:
                frame, overflowed = stream.read(
                    FRAME_SIZE
                )

                level = audio_level(frame)

                if level >= threshold:
                    active_frames += 1
                else:
                    active_frames = 0

                if active_frames >= INTERRUPT_FRAMES:
                    stop_process(process)
                    print("🎙️ Voice interruption detected.")
                    return True
            else:
                time.sleep(0.03)

        if process.returncode != 0:
            raise subprocess.CalledProcessError(
                process.returncode, command
            )

        return False

    finally:
        if process is not None:
            stop_process(process)

        if stream is not None:
            stream.stop()
            stream.close()


async def synthesize(text, voice, path):
    communicator = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=SPEECH_RATE
    )
    await communicator.save(str(path))


async def speak_edge(text, language):
    segments = (
        split_tanglish(text)
        if language == "tanglish"
        else [(language, text)]
    )

    if not segments:
        return False

    with tempfile.TemporaryDirectory() as directory:
        audio_files = []

        # Generate audio first, before monitoring the mic.
        for index, (segment_language, segment_text) in enumerate(
            segments
        ):
            path = Path(directory) / f"ria_{index}.mp3"

            await synthesize(
                segment_text,
                choose_voice(segment_language),
                path
            )

            audio_files.append(path)

        for path in audio_files:
            interrupted = play_interruptible(
                ["afplay", str(path)]
            )

            if interrupted:
                return True

    return False


def speak_macos(text):
    return play_interruptible(
        [
            "say",
            "-v",
            MAC_VOICE,
            "-r",
            "155",
            text
        ]
    )


def speak(text, language="english"):
    if not text or not text.strip():
        return False

    text = prepare_text(text)

    if TTS_ENGINE == "macos":
        return speak_macos(text)

    try:
        return asyncio.run(
            speak_edge(text, language)
        )

    except Exception as exc:
        print(f"Neural TTS error: {exc}")
        print("Using macOS fallback.")
        return speak_macos(text)


if __name__ == "__main__":
    speak(
        "Hello, I'm Ria. I'm explaining something "
        "interesting. You can interrupt me "
        "by speaking at any time.",
        "english"
    )
