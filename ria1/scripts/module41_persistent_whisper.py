
"""Persistent, framed Whisper worker. No application API imports."""

import base64
import contextlib
import io
import json
import sys

from ria1.scripts import module11_whisper_worker as original


def main():
    # Load once, retaining the original English model configuration.
    import os

    model_path = os.getenv(
        "RIA_WHISPER_MODEL_PATH",
        "Systran/faster-whisper-base",
    )

    model = original.WhisperModel(
        model_path,
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        num_workers=1,
        local_files_only=True,
    )

    original.WhisperModel = lambda *args, **kwargs: model

    print(json.dumps({"type": "ready"}), flush=True)

    real_stdin = sys.stdin

    for line in real_stdin:
        try:
            request = json.loads(line)
            raw = base64.b64decode(
                request["audio"], validate=True
            )

            output = io.StringIO()

            class Input:
                buffer = io.BytesIO(raw)

            try:
                sys.stdin = Input()
                with contextlib.redirect_stdout(output):
                    original.main()
            finally:
                sys.stdin = real_stdin

            result = json.loads(output.getvalue().strip())
            print(
                json.dumps({"type": "result", "data": result}),
                flush=True,
            )

        except Exception as exc:
            print(
                json.dumps({
                    "type": "error",
                    "error": type(exc).__name__,
                    "message": str(exc)[:200],
                }),
                flush=True,
            )


if __name__ == "__main__":
    main()
