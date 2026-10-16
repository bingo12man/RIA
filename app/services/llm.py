
import httpx

from app.core.config import OLLAMA_URL, OLLAMA_MODEL


class LLMError(Exception):
    pass


async def generate_reply(messages: list[dict]) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 350
        }
    }

    try:
        async with httpx.AsyncClient(
            timeout=120.0,
            trust_env=False
        ) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload
            )

            response.raise_for_status()

            result = response.json()
            reply = result["message"]["content"].strip()

            if not reply:
                raise LLMError("The AI model returned an empty reply.")

            return reply

    except httpx.RequestError as exc:
        raise LLMError(
            "Cannot connect to local Ollama."
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise LLMError(
            "Ollama failed to generate a response."
        ) from exc

    except (KeyError, TypeError, ValueError) as exc:
        raise LLMError(
            "Ollama returned an invalid response."
        ) from exc
