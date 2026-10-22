"""RIA cloud speech recognition with local noise rejection."""

import io
import os
import time
import wave

import numpy as np

from ria1.scripts.module13_transient_filter import analyze_audio


def transcribe_wav(wav_bytes: bytes) -> dict:
    start = time.perf_counter()

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        if (
            wav.getframerate() != 16000
            or wav.getnchannels() != 1
            or wav.getsampwidth() != 2
        ):
            raise ValueError("Expected 16kHz mono 16-bit PCM WAV")

        pcm = wav.readframes(wav.getnframes())

    audio = (
        np.frombuffer(pcm, dtype="<i2")
        .astype(np.float32) / 32768.0
    )

    if audio.size == 0:
        raise ValueError("Empty audio")

    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(audio)))

    if rms < 0.003 and peak < 0.02:
        return {
            "text": "",
            "rejected": True,
            "rejection_reason": "silence",
            "backend": "groq",
            "inference_seconds": 0.0,
        }

    noise = analyze_audio(audio)

    if noise["transient_only"]:
        return {
            "text": "",
            "rejected": True,
            "rejection_reason": "transient_noise",
            "backend": "groq",
            "inference_seconds": 0.0,
        }

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not configured")

    from groq import Groq

    client = Groq(timeout=5.0, max_retries=1)

    response = client.audio.transcriptions.create(
        file=("ria_audio.wav", wav_bytes),
        model="whisper-large-v3-turbo",
        response_format="json",
        language="en",
        temperature=0,

    )

    transcript = response.text.strip()

    # Reject a known hallucination from silent recordings.
    if transcript.lower().strip(" .!?") == "the assistant's name is ria":
        return {
            "text": "",
            "rejected": True,
            "rejection_reason": "known_hallucination",
            "backend": "groq",
            "inference_seconds": round(time.perf_counter() - start, 2),
        }


    recognized = response.text.strip()

    if recognized.casefold().rstrip(".!? ") == "the assistant's name is ria":
        return {
            "text": "",
            "rejected": True,
            "rejection_reason": "prompt_echo",
            "backend": "groq",
            "inference_seconds": round(time.perf_counter() - start, 2),
        }

    return {
        "text": recognized,
        "rejected": not bool(response.text.strip()),
        "rejection_reason": None if response.text.strip() else "empty_transcript",
        "backend": "groq",
        "inference_seconds": round(time.perf_counter() - start, 2),
    }
