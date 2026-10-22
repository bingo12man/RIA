"""RIA cloud and local LLM providers."""

import json
import os
import urllib.request

CLOUD_MODEL = "openai/gpt-oss-120b"
LOCAL_MODEL = "qwen2.5:3b"


def ask_groq(messages, max_tokens=250):
    """Run Groq in the isolated environment to avoid slow imports."""
    import subprocess
    import sys
    import time
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    python = root / ".venv" / "bin" / "python"

    if not python.is_file():
        raise RuntimeError("Clean Groq Python environment not found")

    payload = json.dumps({
        "messages": messages,
        "max_tokens": max_tokens,
    })

    started = time.perf_counter()

    try:
        result = subprocess.run(
            [
                str(python),
                "-m",
                "ria1.scripts.module14_groq_llm_runner",
            ],
            input=payload,
            text=True,
            capture_output=True,
            cwd=str(root),
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            "Groq LLM subprocess exceeded 20 seconds"
        ) from exc

    if result.returncode:
        raise RuntimeError(
            "Groq LLM subprocess failed: "
            + result.stderr[-1200:]
        )

    data = json.loads(result.stdout)
    reply = data["reply"].strip()

    if not reply:
        raise RuntimeError("Empty Groq reply")

    print(
        f"RIA GROQ BRIDGE | elapsed="
        f"{time.perf_counter() - started:.2f}s",
        flush=True,
    )

    return reply


def ask_local(messages, max_tokens=250):
    payload = {
        "model": LOCAL_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_ctx": 2048,
            "num_predict": max_tokens,
        },
    }

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)

    reply = result.get("message", {}).get("content", "").strip()

    if not reply:
        raise RuntimeError("Empty local model response")

    return reply


def ask_ria(messages, max_tokens=250):
    import time

    provider = os.getenv("RIA_LLM_PROVIDER", "local").lower()

    started = time.perf_counter()

    print(
        f"RIA LLM REQUEST START | provider={provider} | "
        f"key_available={bool(os.getenv('GROQ_API_KEY'))}",
        flush=True,
    )

    if provider == "groq":
        try:
            reply = ask_groq(messages, max_tokens)

            print(
                "RIA LLM PROVIDER: groq | "
                f"elapsed={time.perf_counter()-started:.2f}s",
                flush=True,
            )
            return reply

        except Exception as exc:
            print(
                "RIA GROQ ERROR:",
                type(exc).__name__,
                str(exc)[:300],
                flush=True,
            )
            raise

    if provider == "local":
        reply = ask_local(messages, max_tokens)

        print(
            "RIA LLM PROVIDER: local | "
            f"elapsed={time.perf_counter()-started:.2f}s",
            flush=True,
        )
        return reply

    raise ValueError(f"Unknown LLM provider: {provider}")
