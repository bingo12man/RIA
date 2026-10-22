import numpy as np
import torch
from silero_vad import load_silero_vad, get_speech_timestamps

from ria1.cloud.safe_recording import record_safely, SAMPLE_RATE


def main():
    model = load_silero_vad()

    audio = record_safely()

    if audio is None:
        print("RESULT: REJECTED — low audio level")
        return

    waveform = torch.from_numpy(
        np.asarray(audio, dtype=np.float32)
    )

    segments = get_speech_timestamps(
        waveform,
        model,
        sampling_rate=SAMPLE_RATE,
        threshold=0.65,
        min_speech_duration_ms=300,
        min_silence_duration_ms=400,
    )

    speech_seconds = sum(
        (segment["end"] - segment["start"]) / SAMPLE_RATE
        for segment in segments
    )

    print("Speech segments:", len(segments))
    print(f"Speech duration: {speech_seconds:.2f}s")

    if speech_seconds < 0.5:
        print("RESULT: REJECTED — insufficient speech")
    else:
        print("RESULT: ACCEPTED — speech detected")


if __name__ == "__main__":
    main()
