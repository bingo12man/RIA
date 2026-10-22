"""Dynamic GPT-OSS duplicate confirmation subprocess."""

import json
import sys
from ria1.scripts.module29_duplicate_confirmation_runner import SYSTEM_POLICY


def main():
    payload = json.load(sys.stdin)
    message = payload["message"]
    proposal = payload["proposal"]

    if not isinstance(message, str) or not message.strip():
        raise ValueError("Invalid confirmation message")
    if not isinstance(proposal, dict):
        raise ValueError("Invalid proposal")

    title = proposal.get("title")
    due_at = proposal.get("due_at")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Invalid title")
    if type(due_at) is not int or due_at <= 0:
        raise ValueError("Invalid timestamp")

    import os
    import subprocess
    import tempfile

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing")

    if "\\n" in api_key or "\\r" in api_key:
        raise ValueError("Invalid API key")

    def curl_quote(value):
        return '"' + value.replace("\\\\", "\\\\\\\\").replace('"', '\\\\"') + '"'

    body_payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": SYSTEM_POLICY},
            {
                "role": "user",
                "content": json.dumps({
                    "pending_duplicate": proposal,
                    "user_answer": message,
                }, ensure_ascii=False),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 200,
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="ria_duplicate_confirmation_",
        suffix=".json",
    ) as body:
        json.dump(body_payload, body, ensure_ascii=False)
        body.flush()

        config = "\n".join([
            "silent",
            "show-error",
            "fail-with-body",
            "max-time = 15",
            'request = "POST"',
            "url = " + curl_quote(
                "https://api.groq.com/openai/v1/chat/completions"
            ),
            "header = " + curl_quote("Content-Type: application/json"),
            "header = " + curl_quote(
                "Authorization: Bearer " + api_key
            ),
            "data-binary = " + curl_quote("@" + body.name),
            "",
        ])

        process = subprocess.run(
            ["curl", "--config", "-"],
            input=config,
            capture_output=True,
            text=True,
            timeout=18,
            check=False,
        )

    if process.returncode:
        raise RuntimeError(
            "Duplicate confirmation request failed: "
            + (process.stdout + process.stderr)[-600:]
        )

    response_data = json.loads(process.stdout)
    content = response_data["choices"][0]["message"].get("content")

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Empty duplicate confirmation response")

    result = json.loads(content)
    if not isinstance(result, dict) or set(result) != {"decision"}:
        raise ValueError("Invalid confirmation response")
    if result["decision"] not in {
        "confirm", "decline", "clarify", "unrelated"
    }:
        raise ValueError("Invalid confirmation decision")

    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
