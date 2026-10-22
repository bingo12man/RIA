import io
import subprocess

import numpy as np


MAX_DURATION_SECONDS = 30


def webm_to_whisper_bytes(webm_bytes: bytes) -> bytes:
    """Convert browser audio into a NumPy byte stream for Whisper."""

    if not webm_bytes:
        raise ValueError("Empty audio recording")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-i", "pipe:0",
        "-t", str(MAX_DURATION_SECONDS),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "f32le",
        "pipe:1",
    ]

    try:
        result = subprocess.run(
            command,
            input=webm_bytes,
            capture_output=True,
            timeout=20,
            check=True,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("Audio conversion timed out")
    except subprocess.CalledProcessError as exc:
        raise ValueError("Invalid or unsupported audio recording") from exc

    audio = np.frombuffer(result.stdout, dtype="<f4").copy()

    if audio.size == 0:
        raise ValueError("No audio samples found")

    output = io.BytesIO()
    np.save(output, audio, allow_pickle=False)

    return output.getvalue()
