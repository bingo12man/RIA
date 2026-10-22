import io
import time
import numpy as np
import modal

from voice.recording import record_until_silence

print("Recording one sentence...")
audio = record_until_silence()

if audio is None:
    print("No speech detected.")
else:
    buffer = io.BytesIO()
    np.save(buffer, audio, allow_pickle=False)

    started = time.perf_counter()

    service = modal.Cls.from_name(
        "ria-whisper",
        "WhisperService",
    )

    result = service().transcribe.remote(
        buffer.getvalue()
    )

    print("Transcription:", result["text"])
    print("Language:", result["language"])
    print(
        "Cloud round-trip:",
        round(time.perf_counter() - started, 2),
        "seconds",
    )
