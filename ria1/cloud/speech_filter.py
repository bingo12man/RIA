import numpy as np
import torch
from functools import lru_cache
from silero_vad import load_silero_vad, get_speech_timestamps

SAMPLE_RATE = 16000


@lru_cache(maxsize=1)
def get_vad_model():
    return load_silero_vad()


def validate_speech(audio):
    if audio is None:
        return False

    audio = np.asarray(audio, dtype=np.float32).flatten()

    if audio.size == 0 or not np.all(np.isfinite(audio)):
        print("[VAD] Invalid audio.")
        return False

    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio ** 2)))

    print(f"[Audio] Peak: {peak:.4f}, RMS: {rms:.4f}")

    if rms < 0.008 or peak < 0.025:
        print("[VAD] Rejected: audio too quiet.")
        return False

    # Avoid feeding extreme recording spikes to VAD.
    audio = np.clip(audio, -1.0, 1.0)

    waveform = torch.from_numpy(audio)

    segments = get_speech_timestamps(
        waveform,
        get_vad_model(),
        sampling_rate=SAMPLE_RATE,
        threshold=0.65,
        min_speech_duration_ms=300,
        min_silence_duration_ms=400,
    )

    duration = sum(
        (s["end"] - s["start"]) / SAMPLE_RATE
        for s in segments
    )

    print(f"[VAD] Speech duration: {duration:.2f}s")

    if duration < 0.5:
        print("[VAD] Rejected: insufficient speech.")
        return False

    print("[VAD] Accepted.")
    return True
