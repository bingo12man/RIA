import modal

app = modal.App("ria-qwen-cache")

volume = modal.Volume.from_name(
    "ria-qwen-model-cache",
    create_if_missing=True,
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("huggingface_hub>=0.25,<1")
)

MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
MODEL_PATH = "/models/qwen2.5-3b"


@app.function(
    image=image,
    volumes={"/models": volume},
    timeout=1200,
    max_containers=1,
)
def download_model():
    from huggingface_hub import snapshot_download

    print("Downloading Qwen to persistent storage...")

    snapshot_download(
        repo_id=MODEL_ID,
        local_dir=MODEL_PATH,
        ignore_patterns=[
            "*.bin",
            "*.pt",
            "*.h5",
            "*.onnx",
        ],
    )

    volume.commit()

    print("Model cache saved successfully.")
    return MODEL_PATH


@app.local_entrypoint()
def main():
    path = download_model.remote()
    print("Saved model at:", path)
