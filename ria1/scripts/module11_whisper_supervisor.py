
"""Persistent supervised Whisper with bounded restart recovery."""

import atexit
import base64
from collections import deque
import json
import os
import queue
import subprocess
import sys
import threading
import time

TIMEOUT_SECONDS = 60
STARTUP_TIMEOUT_SECONDS = 90
MAX_AUDIO_BYTES = 3_000_000

_worker_lock = threading.Lock()
_process = None
_responses = None
_recent_errors = deque(maxlen=30)


def _read_stdout(process, responses):
    try:
        for line in process.stdout:
            responses.put(line)
    finally:
        responses.put(None)


def _read_stderr(process):
    for line in process.stderr:
        _recent_errors.append(line.rstrip())


def _stop_worker():
    global _process, _responses

    process = _process
    _process = None
    _responses = None

    if process is None:
        return

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    for stream in (process.stdin, process.stdout, process.stderr):
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _receive(timeout):
    try:
        line = _responses.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError("Speech recognition timed out") from exc

    if line is None:
        raise RuntimeError(
            "Whisper worker exited: "
            + " | ".join(list(_recent_errors)[-5:])
        )

    return json.loads(line)


def _start_worker():
    global _process, _responses

    if _process is not None and _process.poll() is None:
        return

    _stop_worker()
    _recent_errors.clear()

    env = {
        **os.environ,
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
    }

    _process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "ria1.scripts.module41_persistent_whisper",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    _responses = queue.Queue()

    threading.Thread(
        target=_read_stdout,
        args=(_process, _responses),
        daemon=True,
    ).start()

    threading.Thread(
        target=_read_stderr,
        args=(_process,),
        daemon=True,
    ).start()

    try:
        response = _receive(STARTUP_TIMEOUT_SECONDS)

        if response != {"type": "ready"}:
            raise RuntimeError("Invalid Whisper startup response")

    except Exception as exc:
        print(
            "RIA WHISPER STARTUP FAILED | "
            f"python={sys.executable} | "
            f"pid={_process.pid if _process else None} | "
            f"error={type(exc).__name__}: {exc} | "
            f"stderr={list(_recent_errors)}",
            flush=True,
        )
        _stop_worker()
        raise

    print(
        f"RIA WHISPER READY | persistent PID={_process.pid}",
        flush=True,
    )


def transcribe_supervised(whisper_bytes: bytes) -> dict:
    if not isinstance(whisper_bytes, bytes):
        raise TypeError("Audio must be bytes")

    if len(whisper_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("Audio exceeds maximum supported size")

    # RIA_M85_BOUNDED_STT_WAIT
    # Allow a brief wait for an active transcription to finish.
    # Never queue indefinitely behind a slow or failed worker.
    if not _worker_lock.acquire(timeout=12):
        raise RuntimeError(
            "Speech recognizer is busy; please retry shortly"
        )

    started = time.perf_counter()

    try:
        _start_worker()

        request = json.dumps({
            "audio": base64.b64encode(
                whisper_bytes
            ).decode("ascii"),
        })

        try:
            _process.stdin.write(request + "\n")
            _process.stdin.flush()

            response = _receive(TIMEOUT_SECONDS)

            if response.get("type") != "result":
                raise RuntimeError(
                    "Whisper worker error: "
                    + str(response.get("message", "unknown"))
                )

            result = response["data"]

            if not isinstance(result, dict):
                raise ValueError("Invalid transcription result")

            print(
                "RIA PERSISTENT WHISPER | "
                f"roundtrip={time.perf_counter() - started:.2f}s | "
                f"inference={result['inference_seconds']:.2f}s | "
                f"pid={_process.pid}",
                flush=True,
            )

            return result

        except Exception:
            _stop_worker()
            raise

    finally:
        _worker_lock.release()


atexit.register(_stop_worker)
