"""Background-initialized persistent Whisper supervisor."""

import atexit
import base64
import json
import os
import queue
import subprocess
import sys
import threading

STARTUP_TIMEOUT = 180
REQUEST_TIMEOUT = 8

_lock = threading.Lock()
_worker = None
_responses = None
_state = "stopped"
_generation = 0


def _reader(proc, responses):
    try:
        for line in proc.stdout:
            try:
                responses.put(json.loads(line))
            except json.JSONDecodeError:
                responses.put({"status": "error", "error": "bad_json"})
    finally:
        responses.put({"status": "disconnected"})


def _stop_locked():
    global _worker, _responses, _state, _generation

    _generation += 1
    proc = _worker
    _worker = None
    _responses = None
    _state = "stopped"

    if proc is not None and proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass


def _initialize(generation):
    global _worker, _responses, _state

    env = {
        **os.environ,
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
    }

    proc = None

    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                os.getenv(
                    "RIA_WHISPER_WORKER_MODULE",
                    "ria1.scripts.module13_persistent_whisper_worker",
                ),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            bufsize=1,
            text=True,
        )

        responses = queue.Queue()

        threading.Thread(
            target=_reader,
            args=(proc, responses),
            daemon=True,
        ).start()

        with _lock:
            if generation != _generation:
                proc.kill()
                return

            _worker = proc
            _responses = responses

        ready = responses.get(timeout=STARTUP_TIMEOUT)

        if ready.get("status") != "ready":
            raise RuntimeError("Worker startup failed")

        with _lock:
            if generation == _generation:
                _state = "ready"

        print("RIA persistent Whisper: READY", flush=True)

    except Exception as exc:
        print(
            "RIA persistent Whisper startup failed:",
            type(exc).__name__,
            flush=True,
        )

        with _lock:
            if generation == _generation:
                _stop_locked()

        if proc is not None and proc.poll() is None:
            proc.kill()


def start_background():
    global _state, _generation

    with _lock:
        if _state in ("starting", "ready"):
            return

        _generation += 1
        generation = _generation
        _state = "starting"

    threading.Thread(
        target=_initialize,
        args=(generation,),
        daemon=True,
    ).start()


def status():
    with _lock:
        return _state


def transcribe_persistent(whisper_bytes):
    # Return immediately if another request owns the worker.
    if not _lock.acquire(blocking=False):
        raise RuntimeError("Speech recognizer is busy")

    try:
        if _state != "ready" or _worker is None:
            raise RuntimeError("Speech recognizer is warming up")

        if _worker.poll() is not None:
            _stop_locked()
            raise RuntimeError("Speech recognizer disconnected")

        payload = json.dumps({
            "audio": base64.b64encode(whisper_bytes).decode("ascii")
        })

        try:
            _worker.stdin.write(payload + "\n")
            _worker.stdin.flush()
            result = _responses.get(timeout=REQUEST_TIMEOUT)

        except queue.Empty as exc:
            _stop_locked()
            raise TimeoutError(
                "Persistent Whisper request timed out"
            ) from exc

        except (BrokenPipeError, OSError) as exc:
            _stop_locked()
            raise RuntimeError(
                "Persistent Whisper worker disconnected"
            ) from exc

        if result.get("status") != "ok":
            _stop_locked()
            raise RuntimeError("Persistent Whisper worker failed")

        return result["result"]

    finally:
        _lock.release()


def transcribe_with_recovery(whisper_bytes):
    """Transcribe and schedule recovery after worker failure."""
    try:
        return transcribe_persistent(whisper_bytes)

    except (TimeoutError, RuntimeError) as exc:
        message = str(exc).lower()

        # Another request already owns the worker.
        # Do not interfere with its execution.
        if "busy" in message:
            raise

        # If the worker is stopped, start a replacement.
        # Background initialization does not block this request.
        if status() == "stopped":
            start_background()

        raise


def shutdown():
    with _lock:
        _stop_locked()


atexit.register(shutdown)
