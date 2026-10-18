import os
import time
import uuid

import httpx
import numpy as np
from faster_whisper import WhisperModel

from voice.recording import record_until_silence
from voice.tts import synthesize_to_pcm
from voice.audio_player import ContinuousAudioPlayer


# ==================================================
# RIA-1 — MODULE 5.8
# Voice + Conversation + Persistent Memory
# ==================================================

RIA_API = os.getenv(
    "RIA_CONVERSATION_API",
    "http://127.0.0.1:8000/conversation",
).rstrip("/")

WHISPER_SIZE = os.getenv(
    "RIA_WHISPER_MODEL", "small"
)

# Consistent ID across the entire voice session.
session_id = str(uuid.uuid4())


def transcribe(model, audio):
    started = time.perf_counter()

    segments, info = model.transcribe(
        np.asarray(audio, dtype=np.float32),
        beam_size=2,
        vad_filter=True,
    )

    text = " ".join(
        segment.text.strip()
        for segment in segments
    ).strip()

    print(
        f"[STT] {time.perf_counter() - started:.2f}s"
    )
    print(f"[Detected language] {info.language}")

    return text


def get_ria_reply(message):
    global session_id

    payload = {
        "message": message,
        "session_id": session_id,
    }

    started = time.perf_counter()

    with httpx.Client(
        timeout=240.0,
        trust_env=False,
    ) as client:
        response = client.post(
            f"{RIA_API}/chat",
            json=payload,
        )

        response.raise_for_status()
        result = response.json()

    session_id = result["session_id"]

    print(
        f"[LLM] {time.perf_counter() - started:.2f}s"
    )
    print(
        f"[History] {result['history_messages']} messages"
    )
    print(
        f"[Style] {result['response_style']}"
    )
    print(
        f"[Language route] {result['language_route']}"
    )

    return result["reply"]


def speak(text):
    started = time.perf_counter()

    # Module 5 currently replies in English.
    audio = synthesize_to_pcm(
        text,
        language="english",
    )

    print(
        f"[TTS] {time.perf_counter() - started:.2f}s"
    )

    if len(audio) == 0:
        print("[Voice] No audio generated.")
        return

    with ContinuousAudioPlayer() as player:
        player.play(audio)


def main():
    print("=" * 50)
    print("RIA-1 — MODULE 5.8")
    print("Voice + Conversation + Memory")
    print("=" * 50)

    print("Conversation API:", RIA_API)
    print("Session:", session_id)

    print("\nLoading Whisper model...")

    model = WhisperModel(
        WHISPER_SIZE,
        device="cpu",
        compute_type="int8",
    )

    print("Whisper ready.")
    print("Ria is ready to listen.")
    print("Press Ctrl+C to quit.\n")

    while True:
        try:
            audio = record_until_silence()

            if audio is None:
                continue

            text = transcribe(model, audio)

            if not text:
                print("[RIA] No speech recognized.")
                continue

            print("\nYOU:", text)

            # A deliberately simple local exit command.
            if text.lower().strip(" .!?") in {
                "exit ria",
                "quit ria",
                "stop listening ria",
            }:
                print("RIA: Goodbye!")
                break

            try:
                reply = get_ria_reply(text)
            except httpx.HTTPError as error:
                print("[API ERROR]", error)
                continue
            except (ValueError, KeyError) as error:
                print("[RESPONSE ERROR]", error)
                continue

            print("\nRIA:", reply)

            try:
                speak(reply)
            except Exception as error:
                print("[AUDIO ERROR]", error)

            print("\nReady for your next message.")

        except KeyboardInterrupt:
            print("\nRIA stopped.")
            break


if __name__ == "__main__":
    main()
