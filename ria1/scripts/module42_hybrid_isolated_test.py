
"""Isolated hybrid integration test launcher."""

import os
import sys
import uvicorn

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "ria1/data/hybrid_isolated_test"

TEST_DIR.mkdir(parents=True, exist_ok=True)

os.environ["RIA_AGENT_LEDGER_DB"] = str(
    TEST_DIR / "agent_actions.sqlite3"
)
os.environ["RIA_HYBRID_AGENT_ENABLED"] = "1"
os.environ["RIA_NATIVE_AGENT_ENABLED"] = "0"
os.environ["RIA_AGENT_ENABLED"] = "0"
os.environ["RIA_STT_BACKEND"] = "local"

# Use the verified cached model path for isolated voice testing.
snapshots = (
    Path.home()
    / ".cache/huggingface/hub"
    / "models--Systran--faster-whisper-base"
    / "snapshots"
)
model_dirs = sorted(
    p for p in snapshots.iterdir()
    if p.is_dir() and (p / "model.bin").is_file()
)
if len(model_dirs) != 1:
    raise RuntimeError("Expected exactly one cached Whisper snapshot")

os.environ["RIA_WHISPER_MODEL_PATH"] = str(model_dirs[0])

from ria1.scripts import module8_command_executor

module8_command_executor.REMINDER_API = (
    "http://127.0.0.1:8021"
)

from ria1.scripts import module7_audio_api

# Never delete real conversation sessions during testing.
module7_audio_api._delete_old_conversation_session = (
    lambda session_id: True
)

if __name__ == "__main__":
    uvicorn.run(
        module7_audio_api.app,
        host="127.0.0.1",
        port=8022,
        access_log=False,
    )
