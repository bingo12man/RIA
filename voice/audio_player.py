
import select
import sys
import time

import numpy as np
import sounddevice as sd


SAMPLE_RATE = 24000
BLOCK_SIZE = 960


def keyboard_interrupted():
    """
    Detect an Enter keypress during playback.
    """

    if not sys.stdin.isatty():
        return False

    ready, _, _ = select.select(
        [sys.stdin], [], [], 0
    )

    if not ready:
        return False

    sys.stdin.readline()
    return True


class ContinuousAudioPlayer:
    """
    Persistent audio player for a single conversation.

    Each synthesized sentence is played through
    the same sounddevice output stream.
    """

    def __init__(self):
        self.stream = None
        self.interrupted = False
        self.total_samples = 0
        self.started_at = None

    def __enter__(self):
        self.stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE
        )

        self.stream.start()
        self.started_at = time.perf_counter()

        print("🔊 Ria is speaking.")
        print("Press ENTER to interrupt.")

        return self

    def play(self, audio):
        """
        Play PCM audio in small chunks.

        Returns True when interrupted.
        """
        if self.interrupted:
            return True

        samples = np.asarray(
            audio,
            dtype=np.float32
        ).flatten()

        for offset in range(
            0,
            len(samples),
            BLOCK_SIZE
        ):
            if keyboard_interrupted():
                self.interrupted = True
                print("⏹️ Speech interrupted.")
                return True

            chunk = samples[
                offset:offset + BLOCK_SIZE
            ]

            # Keep the final chunk at its actual
            # size rather than padding it with silence.
            self.stream.write(
                np.ascontiguousarray(
                    chunk.reshape(-1, 1)
                )
            )

            self.total_samples += len(chunk)

        return False

    def __exit__(self, exc_type, exc_value, traceback):
        if self.stream is not None:
            if self.interrupted:
                # Immediately discard queued playback.
                self.stream.abort()
            else:
                # Finish any remaining buffered samples.
                self.stream.stop()

            self.stream.close()
            self.stream = None

        self.started_at = None
