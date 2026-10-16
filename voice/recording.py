
from collections import deque
import time

import numpy as np
import sounddevice as sd


SAMPLE_RATE = 16000
FRAME_SECONDS = 0.03

START_TIMEOUT = 10.0
MAX_RECORD_SECONDS = 20.0
SILENCE_SECONDS = 0.9

MIN_THRESHOLD = 0.012
NOISE_MULTIPLIER = 3.0


def audio_energy(audio):
    """Calculate the loudness of an audio frame."""
    samples = np.asarray(audio, dtype=np.float32)

    if samples.size == 0:
        return 0.0

    return float(np.sqrt(np.mean(samples ** 2)))


def get_threshold(noise_levels):
    """Choose a threshold using the room's noise level."""
    average_noise = float(np.mean(noise_levels))

    return max(
        MIN_THRESHOLD,
        average_noise * NOISE_MULTIPLIER
    )


def record_until_silence():
    """Record one utterance and stop after silence."""

    frame_size = int(SAMPLE_RATE * FRAME_SECONDS)
    preroll = deque(maxlen=10)

    captured = []
    speaking = False
    last_sound_time = None

    print("\n🎙️ Calibrating microphone...")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=frame_size
    ) as stream:

        # Sample the room noise for half a second.
        noise_levels = []

        for _ in range(17):
            frame, overflowed = stream.read(frame_size)
            noise_levels.append(audio_energy(frame))

        threshold = get_threshold(noise_levels)

        print("RIA is listening. Speak now.")

        start_time = time.monotonic()

        while True:
            frame, overflowed = stream.read(frame_size)

            frame = frame[:, 0].copy()
            energy = audio_energy(frame)

            current_time = time.monotonic()

            if not speaking:
                preroll.append(frame)

                if energy >= threshold:
                    speaking = True
                    last_sound_time = current_time

                    captured.extend(preroll)
                    preroll.clear()

                    print("Speech detected...")

                elif current_time - start_time >= START_TIMEOUT:
                    print("No speech detected.")
                    return None

            else:
                captured.append(frame)

                if energy >= threshold:
                    last_sound_time = current_time

                elif (
                    current_time - last_sound_time
                    >= SILENCE_SECONDS
                ):
                    print("End of speech detected.")
                    break

                if (
                    current_time - start_time
                    >= MAX_RECORD_SECONDS
                ):
                    print("Maximum recording length reached.")
                    break

    if not captured:
        return None

    return np.concatenate(captured).astype(np.float32)
