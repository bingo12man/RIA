"""Local Whisper transcription for RIA-1."""

import io
import threading
import time

import numpy as np

MODEL_NAME = "Systran/faster-whisper-base"

_model = None
_model_lock = threading.Lock()
_inference_lock = threading.Lock()


def get_model():
    global _model

    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel

                started = time.perf_counter()

                _model = WhisperModel(
                    MODEL_NAME,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4,
                    num_workers=1,
                    local_files_only=True,
                )

                print(
                    f"RIA LOCAL WHISPER model loaded in "
                    f"{time.perf_counter() - started:.2f}s",
                    flush=True,
                )

    return _model


def transcribe_local(whisper_bytes: bytes) -> dict:
    audio = np.load(
        io.BytesIO(whisper_bytes),
        allow_pickle=False,
    )

    started = time.perf_counter()

    model = get_model()

    # One transcription at a time on this 8 GB Mac.
    with _inference_lock:
        segments, info = model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt="Ria is a friendly voice assistant.",
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

    elapsed = time.perf_counter() - started

    print(
        f"RIA LOCAL WHISPER transcription: {elapsed:.2f}s",
        flush=True,
    )

    return {
        "text": text,
        "language": info.language,
        "inference_seconds": round(elapsed, 2),
    }
