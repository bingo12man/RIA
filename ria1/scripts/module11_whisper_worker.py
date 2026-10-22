"""One-shot, isolated Whisper worker."""

import io
import json
import sys
import time

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.vad import (
    get_speech_timestamps,
    VadOptions,
)


def main():
    started = time.perf_counter()

    print("RIA WORKER | starting", file=sys.stderr, flush=True)

    audio_bytes = sys.stdin.buffer.read()
    audio = np.load(io.BytesIO(audio_bytes), allow_pickle=False)

    if audio.ndim != 1 or audio.size == 0:
        raise ValueError("Invalid audio samples")

    if not np.all(np.isfinite(audio)):
        raise ValueError("Audio contains invalid samples")

    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(audio)))

    # Conservative silence gate.
    if rms < 0.003 and peak < 0.02:
        print(json.dumps({
            "text": "",
            "language": "en",
            "inference_seconds": 0.0,
            "silence_detected": True,
        }), flush=True)
        return

    # P0.1: Detect likely human speech before transcription.
    # Audio is already converted to 16 kHz mono PCM.
    speech_segments = get_speech_timestamps(
        audio,
        vad_options=VadOptions(
            threshold=0.5,
            min_speech_duration_ms=250,
            min_silence_duration_ms=300,
            speech_pad_ms=100,
        ),
        sampling_rate=16000,
    )

    speech_duration = sum(
        (segment["end"] - segment["start"]) / 16000
        for segment in speech_segments
    )

    if not speech_segments or speech_duration < 0.25:
        print(json.dumps({
            "text": "",
            "language": "en",
            "inference_seconds": round(
                time.perf_counter() - started, 2
            ),
            "speech_detected": False,
            "rejected": True,
            "rejection_reason": "no_speech_activity",
        }), flush=True)
        return

    print(
        f"RIA WORKER | VAD complete at "
        f"{time.perf_counter() - started:.2f}s",
        file=sys.stderr,
        flush=True,
    )

    model = WhisperModel(
        "Systran/faster-whisper-base",
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        num_workers=1,
        local_files_only=True,
    )

    print(
        f"RIA WORKER | model loaded at "
        f"{time.perf_counter() - started:.2f}s",
        file=sys.stderr,
        flush=True,
    )

    segments, info = model.transcribe(
        audio,
        language="en",
        beam_size=1,
        vad_filter=False,
        condition_on_previous_text=False,
    )

    # Materialize lazy segments exactly once.
    segments = list(segments)

    print(
        f"RIA WORKER | inference complete at "
        f"{time.perf_counter() - started:.2f}s",
        file=sys.stderr,
        flush=True,
    )

    transcript = " ".join(
        segment.text.strip() for segment in segments
    ).strip()

    no_speech = max(
        (float(segment.no_speech_prob) for segment in segments),
        default=0.0,
    )

    avg_logprob = (
        sum(float(segment.avg_logprob) for segment in segments)
        / len(segments)
        if segments else 0.0
    )

    # Do not route obvious noise fragments as commands.
    fillers = {
        "oh", "uh", "um", "hmm", "ah", "eh",
        "huh", "mmm",
    }

    normalized = transcript.lower().strip(" .,!?")

    filler_only = normalized in fillers

    # Conservative filtering: strong silence evidence combined
    # with low recognition confidence.
    low_confidence = (
        bool(segments)
        and no_speech > 0.75
        and avg_logprob < -0.8
    )

    rejected = filler_only or low_confidence

    result = {
        "text": "" if rejected else transcript,
        "language": info.language,
        "inference_seconds": round(
            time.perf_counter() - started, 2
        ),
        "rejected": rejected,
        "rejection_reason": (
            "filler_only" if filler_only
            else "low_confidence" if low_confidence
            else None
        ),
        "no_speech_prob": round(no_speech, 3),
        "avg_logprob": round(avg_logprob, 3),
    }

    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
