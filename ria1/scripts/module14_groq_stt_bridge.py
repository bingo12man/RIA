"""Run Groq STT in RIA's clean Python environment."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv-ria-stt/bin/python"

def transcribe_via_bridge(wav_bytes):
    env = os.environ.copy()

    result = subprocess.run(
        [
            str(PYTHON),
            "-m",
            "ria1.scripts.module14_groq_stt_runner",
        ],
        input=wav_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(ROOT),
        timeout=17,
    )

    if result.returncode:
        raise RuntimeError(
            result.stderr.decode(errors="replace")[-1000:]
        )

    return json.loads(result.stdout.decode())
