import modal

app = modal.App("ria-gpu-test")

@app.function(
    gpu="T4",
    timeout=120,
    scaledown_window=2,
)
def check_gpu():
    import subprocess

    result = subprocess.run(
        ["nvidia-smi"],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout

@app.local_entrypoint()
def main():
    print("Checking Modal GPU...")
    print(check_gpu.remote())
