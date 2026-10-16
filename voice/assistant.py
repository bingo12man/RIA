
import os
import re
import subprocess

import httpx
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


RIA_API = "http://127.0.0.1:8000/chat"

SAMPLE_RATE = 16000
RECORD_SECONDS = 6

MODEL_SIZE = os.getenv("RIA_WHISPER_MODEL", "small")
ENGLISH_VOICE = os.getenv("RIA_ENGLISH_VOICE", "Samantha")

# Initialize once instead of loading for every request.
whisper = WhisperModel(
    MODEL_SIZE,
    device="cpu",
    compute_type="int8"
)


def record_audio():
    print("\n🎙️ RIA is listening...")

    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32"
    )

    sd.wait()

    return audio.flatten()


def transcribe_audio(audio):
    print("📝 Transcribing...")

    # Whisper supports NumPy waveform input.
    segments, info = whisper.transcribe(
        np.asarray(audio, dtype=np.float32),
        beam_size=3,
        vad_filter=True
    )

    text = " ".join(
        segment.text.strip()
        for segment in segments
    ).strip()

    return text, info.language


def talk_to_ria(text, session_id, language="auto"):
    payload = {
        "message": text,
        "language": language
    }

    if session_id is not None:
        payload["session_id"] = session_id

    with httpx.Client(
        timeout=180.0,
        trust_env=False
    ) as client:
        response = client.post(
            RIA_API,
            json=payload
        )

        response.raise_for_status()
        return response.json()


def available_voices():
    result = subprocess.run(
        ["say", "-v", "?"],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout


def speak(text, language="english"):
    # Avoid reading empty text.
    if not text.strip():
        return
    text = re.sub(r"\bRIA\b", "Ria", text, flags=re.IGNORECASE)
    voices = available_voices()
    voice = ENGLISH_VOICE

    # Tamil TTS isn't configured yet.
    # Do not misrepresent English synthesis as Tamil TTS.
    if language in ("tamil", "tanglish"):
        print(
            "Tamil/Tanglish voice is provisional. "
            "Testing with the installed macOS voice."
        )

    if voice not in voices:
        voice = None

    command = ["say"]

    if voice:
        command += ["-v", voice]

    command.append(text)

    subprocess.run(command, check=True)


def main():
    print("=" * 45)
    print("RIA — Personal AI Voice Companion")
    print("=" * 45)
    print("Press ENTER to record.")
    print("Type q and ENTER to exit.")

    session_id = None

    while True:
        action = input("\nPress ENTER to speak: ")

        if action.lower().strip() == "q":
            print("RIA voice session ended.")
            break

        try:
            audio = record_audio()

            # Don't treat completely silent input as speech.
            if np.max(np.abs(audio)) < 0.005:
                print("No clear audio detected.")
                continue

            text, detected_language = transcribe_audio(audio)

            if not text:
                print("I couldn't recognize speech.")
                continue

            print(f"\nYou: {text}")
            print(f"Detected: {detected_language}")

            result = talk_to_ria(
                text,
                session_id
            )

            session_id = result["session_id"]

            reply = result["reply"]
            language = result.get("language", "english")

            print(f"\nRIA: {reply}")

            speak(reply, language)

        except KeyboardInterrupt:
            print("\nVoice session stopped.")
            break

        except (
            httpx.HTTPError,
            sd.PortAudioError,
            subprocess.CalledProcessError,
            OSError,
            ValueError
        ) as exc:
            print(f"Voice error: {exc}")


if __name__ == "__main__":
    main()
