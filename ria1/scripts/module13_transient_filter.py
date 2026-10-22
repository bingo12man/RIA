"""Experimental transient-noise rejection for RIA."""

import numpy as np


def analyze_audio(audio, sample_rate=16000):
    audio = np.asarray(audio, dtype=np.float32)

    if audio.ndim != 1 or audio.size == 0:
        raise ValueError("Invalid audio")

    frame_size = int(sample_rate * 0.02)
    count = len(audio) // frame_size

    if count == 0:
        return {
            "longest_active_run": 0.0,
            "active_duration": 0.0,
            "transient_only": False,
        }

    frames = audio[:count * frame_size].reshape(
        count, frame_size
    )

    energy = np.sqrt(
        np.mean(frames.astype(np.float64) ** 2, axis=1)
    )

    active = energy > 0.01

    longest = 0
    current = 0

    for value in active:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    longest_seconds = longest * 0.02
    active_seconds = int(active.sum()) * 0.02

    # Experimental threshold derived from the two recordings.
    transient_only = (
        active_seconds >= 0.1
        and longest_seconds <= 0.12
    )

    return {
        "longest_active_run": round(longest_seconds, 3),
        "active_duration": round(active_seconds, 3),
        "transient_only": transient_only,
    }
