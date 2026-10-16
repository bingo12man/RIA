
import os

import httpx
import numpy as np
from faster_whisper import WhisperModel

from voice.recording import record_until_silence
from voice.tts import speak


RIA_API = "http://127.0.0.1:8000/chat"

MODEL_SIZE = os.getenv(
    "RIA_WHISPER_MODEL",
    "small"
)

whisper = WhisperModel(
    MODEL_SIZE,
    device="cpu",
    compute_type="int8"
)


def transcribe_audio(audio):
    """Convert speech to text."""

    print("📝 Transcribing...")

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
    """Send text to Ria's local AI backend."""

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


def main():
    """Run Ria's voice conversation loop."""

    print("=" * 45)
    print("Ria — Personal AI Voice Companion")
    print("=" * 45)

    print("Press ENTER to speak.")
    print("Recording stops automatically after silence.")
    print("Type q and ENTER to exit.")

    session_id = None

    while True:
        try:
            action = input("\nPress ENTER to speak: ")

            if action.lower().strip() == "q":
                print("Ria voice session ended.")
                break

            audio = record_until_silence()

            if audio is None or audio.size == 0:
                continue

            text, detected_language = transcribe_audio(
                audio
            )

            if not text:
                print("I couldn't recognize your speech.")
                continue

            print(f"\nYou: {text}")
            print(f"Detected language: {detected_language}")

            result = talk_to_ria(
                text,
                session_id
            )

            session_id = result["session_id"]

            reply = result["reply"]
            language = result.get(
                "language",
                "english"
            )

            print(f"\nRia: {reply}")

            speak(reply, language)

        except KeyboardInterrupt:
            print("\nRia voice session stopped.")
            break

        except (
            httpx.HTTPError,
            OSError,
            ValueError
        ) as exc:
            print(f"Voice error: {exc}")


if __name__ == "__main__":
    main()
