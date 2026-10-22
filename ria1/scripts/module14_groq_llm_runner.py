"""RIA GPT-OSS runner using curl without CLI credential exposure."""

import json
import os
import subprocess
import sys
import tempfile

MODEL = "openai/gpt-oss-120b"
URL = "https://api.groq.com/openai/v1/chat/completions"


def curl_quote(value):
    """Escape a value for curl's configuration-file syntax."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    request = json.load(sys.stdin)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing")

    max_tokens = int(request.get("max_tokens", 250))

    payload = {
        "model": MODEL,
        "messages": request["messages"],
        "temperature": 0.3,
        "max_completion_tokens": max(
            160, min(max_tokens * 2, 800)
        ),
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="ria_groq_",
        suffix=".json",
    ) as body:
        json.dump(payload, body)
        body.flush()

        config = "\n".join([
            "silent",
            "show-error",
            "fail-with-body",
            "max-time = 15",
            "request = \"POST\"",
            "url = " + curl_quote(URL),
            "header = " + curl_quote("Content-Type: application/json"),
            "header = " + curl_quote(
                "Authorization: Bearer " + api_key
            ),
            "data-binary = " + curl_quote("@" + body.name),
            "",
        ])

        result = subprocess.run(
            ["curl", "--config", "-"],
            input=config,
            capture_output=True,
            text=True,
            timeout=18,
            check=False,
        )

    if result.returncode:
        raise RuntimeError(
            "Groq request failed: "
            + (result.stdout + result.stderr)[-600:]
        )

    data = json.loads(result.stdout)
    reply = data["choices"][0]["message"].get("content") or ""

    if not reply.strip():
        raise RuntimeError("Empty Groq reply")

    print(json.dumps({"reply": reply.strip()}), flush=True)


if __name__ == "__main__":
    main()
