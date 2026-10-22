from ria1.scripts.module13_transient_filter import analyze_audio
"""Long-running, isolated RIA Whisper worker.

Protocol:
- One JSON request per stdin line.
- One JSON response per stdout line.
- Audio is Base64-encoded NumPy .npy data.
- All diagnostic messages go to stderr.
"""

import base64
import io
import json
import sys
import time

import numpy as np
from faster_whisper import WhisperModel


def log(message):
    print(message, file=sys.stderr, flush=True)


class PersistentWhisper:
    def __init__(self):
        started = time.perf_counter()

        self.model = WhisperModel(
            "Systran/faster-whisper-base",
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            num_workers=1,
            local_files_only=True,
        )

        log(
            "RIA PERSISTENT WHISPER READY | "
            f"load={time.perf_counter() - started:.2f}s"
        )

    def transcribe(self, audio_bytes):
        started = time.perf_counter()

        audio = np.load(
            io.BytesIO(audio_bytes),
            allow_pickle=False,
        )

        if audio.ndim != 1 or audio.size == 0:
            raise ValueError("Invalid audio samples")

        if not np.all(np.isfinite(audio)):
            raise ValueError("Invalid audio values")

        rms = float(
            np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        )
        peak = float(np.max(np.abs(audio)))

        if rms < 0.003 and peak < 0.02:
            return {
                "text": "",
                "language": "en",
                "inference_seconds": 0.0,
                "silence_detected": True,
            }

        noise_check = analyze_audio(audio)

        if noise_check["transient_only"]:
            return {
                "text": "",
                "inference_seconds": 0.0,
                "rejection_reason": "transient_noise",
            }

        segments, info = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )

        segments = list(segments)

        transcript = " ".join(
            segment.text.strip()
            for segment in segments
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

        fillers = {
            "oh", "uh", "um", "hmm",
            "ah", "eh", "huh", "mmm",
        }

        normalized = transcript.lower().strip(" .,!?")
        filler_only = normalized in fillers

        low_confidence = (
            bool(segments)
            and no_speech > 0.75
            and avg_logprob < -0.8
        )

        rejected = filler_only or low_confidence

        return {
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


def main():
    worker = PersistentWhisper()

    # Readiness message on stdout, separate from diagnostics.
    print(json.dumps({"status": "ready"}), flush=True)

    for line in sys.stdin:
        try:
            request = json.loads(line)
            audio_bytes = base64.b64decode(
                request["audio"],
                validate=True,
            )

            result = worker.transcribe(audio_bytes)

            print(
                json.dumps({
                    "status": "ok",
                    "result": result,
                }),
                flush=True,
            )

        except Exception as exc:
            log(
                f"RIA PERSISTENT WORKER ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

            print(
                json.dumps({
                    "status": "error",
                    "error": type(exc).__name__,
                }),
                flush=True,
            )


if __name__ == "__main__":
    main()
