import modal

app = modal.App("ria-whisper-cache")

volume = modal.Volume.from_name(
    "ria-whisper-model-cache",
    create_if_missing=True,
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("huggingface_hub>=0.25,<1")
)


@app.function(
    image=image,
    volumes={"/models": volume},
    timeout=600,
    max_containers=1,
)
def download_model():
    from huggingface_hub import snapshot_download

    print("Caching Whisper Base...")

    snapshot_download(
        repo_id="Systran/faster-whisper-base",
        local_dir="/models/whisper-base",
    )

    volume.commit()
    print("Whisper cache saved successfully.")


@app.local_entrypoint()
def main():
    download_model.remote()
