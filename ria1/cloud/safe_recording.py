import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
RECORD_SECONDS = 5

# Initial thresholds; adjust after inspecting measurements.
MIN_PEAK = 0.025
MIN_RMS = 0.008


def record_safely():
    input(
        "\nPress ENTER when ready to speak "
        "(recording lasts 5 seconds)..."
    )

    print("Recording now. Speak clearly.")

    samples = sd.rec(
        int(SAMPLE_RATE * RECORD_SECONDS),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )

    sd.wait()

    audio = samples.flatten()

    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio ** 2)))

    print(f"Peak level: {peak:.4f}")
    print(f"RMS level:  {rms:.4f}")

    if peak < MIN_PEAK or rms < MIN_RMS:
        print("Rejected: audio level too low.")
        return None

    print("Audio passed initial level check.")
    return audio


if __name__ == "__main__":
    audio = record_safely()
    print(
        "Accepted" if audio is not None
        else "Rejected"
    )
