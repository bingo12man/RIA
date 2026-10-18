
import json
import os

import httpx

from app.core.config import OLLAMA_MODEL, OLLAMA_URL


class LLMError(Exception):
    pass


MAX_OUTPUT_TOKENS = int(
    os.getenv("RIA_MAX_OUTPUT_TOKENS", "600")
)


def ollama_payload(messages, stream=False):
    return {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": stream,
        "think": False,
        "options": {
            "temperature": 0.4,
            "num_ctx": 2048,
            "num_predict": 250
        }
    }


async def generate_reply(messages: list[dict]) -> str:
    """Existing non-streaming API support."""

    try:
        async with httpx.AsyncClient(
            timeout=180.0,
            trust_env=False
        ) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json=ollama_payload(messages)
            )
            response.raise_for_status()

            reply = response.json()["message"]["content"].strip()

            if not reply:
                raise LLMError("The AI returned an empty reply.")

            return reply

    except httpx.HTTPError as exc:
        raise LLMError(
            f"Ollama request failed: {exc}"
        ) from exc

    except (KeyError, ValueError, TypeError) as exc:
        raise LLMError(
            f"Invalid Ollama response: {exc}"
        ) from exc


async def stream_reply(messages: list[dict]):
    """Yield text fragments from Ollama as they arrive."""

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=180.0,
                write=20.0,
                pool=10.0
            ),
            trust_env=False
        ) as client:

            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json=ollama_payload(messages, stream=True)
            ) as response:

                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    data = json.loads(line)

                    if data.get("error"):
                        raise LLMError(str(data["error"]))

                    content = data.get(
                        "message", {}
                    ).get("content", "")

                    if content:
                        yield content

                    if data.get("done"):
                        break

    except httpx.HTTPError as exc:
        raise LLMError(
            f"Ollama streaming failed: {exc}"
        ) from exc

    except (ValueError, TypeError) as exc:
        raise LLMError(
            f"Invalid Ollama stream: {exc}"
        ) from exc
