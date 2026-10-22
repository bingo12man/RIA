# RIA_P11075_CALENDAR_CONTEXT
"""RIA P1.9: validated bridge to LLM-native decision runner."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo
import subprocess
import time
import sys

from ria1.scripts.module15_agent_bridge import ROOT
PYTHON = ROOT / ".venv" / "bin" / "python" 


DECISIONS = {"execute", "clarify", "respond", "reject"}
TOOLS = {
    "memory_save",
    "memory_list",
    "memory_update",
    "memory_forget",
    "reminder_create",
    "reminder_create_absolute",
    "reminder_cancel_lookup",
    "reminder_snooze_lookup",
    "reminder_manage_lookup",
    "reminder_list",
}


def select_native_decision(message, timeout=50, history=None):
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Empty message")

    if len(message) > 4000:
        raise ValueError("Message too long")

    if not PYTHON.is_file():
        raise RuntimeError("Groq environment unavailable")

    from ria1.scripts.module5_memory import get_memories

    # P1102: bounded conversation history, not language parsing.
    if history is None:
        history = []

    if not isinstance(history, list) or len(history) > 24:
        raise ValueError("Invalid conversation history")

    for index, turn in enumerate(history):
        expected_role = "user" if index % 2 == 0 else "assistant"
        if (
            not isinstance(turn, dict)
            or set(turn) != {"role", "content"}
            or turn["role"] != expected_role
            or not isinstance(turn["content"], str)
            or not 0 < len(turn["content"].strip()) <= 4000
        ):
            raise ValueError("Invalid conversation turn")

    if len(history) % 2:
        raise ValueError("Conversation history must contain full exchanges")

    # RIA_M109_DECISION_TIMING
    memory_started = time.perf_counter()
    saved_memories = get_memories("ria_local_owner")
    print(
        f"[RIA_LATENCY] memory_load={time.perf_counter() - memory_started:.3f}s",
        file=sys.stderr,
        flush=True,
    )

    payload = {
        "message": message.strip(),
        "memories": saved_memories,
        "history": history,
        "calendar_context": {
            "current_local_datetime": datetime.now(
                ZoneInfo("Asia/Kolkata")
            ).isoformat(timespec="seconds"),
            "timezone": "Asia/Kolkata",
        },
    }

    subprocess_started = time.perf_counter()

    try:
        process = subprocess.run(
            [
                str(PYTHON),
                "-m",
                "ria1.scripts.module19_decision_runner",
            ],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            cwd=str(ROOT),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("RIA decision timed out") from exc

    print(
        f"[RIA_LATENCY] decision_subprocess={time.perf_counter() - subprocess_started:.3f}s",
        file=sys.stderr,
        flush=True,
    )

    if process.stderr:
        for line in process.stderr.splitlines():
            if "[RIA_LATENCY]" in line:
                print(line, file=sys.stderr, flush=True)

    if process.returncode:
        raise RuntimeError(
            "RIA decision failed: " + process.stderr[-600:]
        )

    result = json.loads(process.stdout)

    if not isinstance(result, dict):
        raise ValueError("Invalid decision object")

    if set(result) != {
        "decision", "tool", "arguments", "reply"
    }:
        raise ValueError("Invalid decision fields")

    decision = result["decision"]
    tool = result["tool"]
    args = result["arguments"]
    reply = result["reply"]

    if decision not in DECISIONS:
        raise ValueError("Unknown decision")

    if not isinstance(args, dict):
        raise ValueError("Invalid arguments")

    if not isinstance(reply, str):
        raise ValueError("Invalid reply")

    if decision == "execute":
        if tool not in TOOLS:
            raise ValueError("Unsupported tool")
        if reply:
            raise ValueError("Execute must not pre-confirm success")
    else:
        if tool is not None or args:
            raise ValueError("Non-execution decision contains a tool")
        if not reply.strip():
            raise ValueError("Missing response")

    return result
