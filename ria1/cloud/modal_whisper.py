import io
import modal

app = modal.App("ria-whisper")

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04",
        add_python="3.11",
    )
    .pip_install(
        "faster-whisper",
        "numpy",
    )
)


@app.cls(
    image=image,
    gpu="T4",
    timeout=120,
    min_containers=0,
    max_containers=1,
    scaledown_window=2,
)
class WhisperService:

    @modal.enter()
    def load(self):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            "base",
            device="cuda",
            compute_type="float16",
        )

    @modal.method()
    def transcribe(self, audio_bytes):
        import numpy as np

        audio = np.load(
            io.BytesIO(audio_bytes),
            allow_pickle=False,
        )

        segments, info = self.model.transcribe(
            audio,
            beam_size=2,
            vad_filter=True,
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

        return {
            "text": text,
            "language": info.language,
        }


@app.local_entrypoint()
def main():
    print("RIA Whisper GPU service configured.")
