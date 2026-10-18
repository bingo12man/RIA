
import json
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.routes import ChatRequest, chat_lock
from app.core.config import OLLAMA_MODEL
from app.core.language_examples import LANGUAGE_EXAMPLES
from app.core.personality import RIA_SYSTEM_PROMPT
from app.services.conversation import conversation_manager
from app.services.language import (
    detect_language,
    get_language_instruction,
    validate_response
)
from app.services.llm import stream_reply, LLMError
from app.services.transliteration import tamil_to_tanglish


router = APIRouter()

SENTENCE_END = re.compile(
    r"(?<=[.!?।！？])\s+|\n+"
)


def encode_event(event_type, **fields):
    return (
        json.dumps(
            {"type": event_type, **fields},
            ensure_ascii=False
        ) + "\n"
    )


def get_ready_sentences(buffer):
    """Return finished sentences and unfinished text."""

    parts = SENTENCE_END.split(buffer)

    if len(parts) > 1:
        return parts[:-1], parts[-1]

    # Prevent an extremely long sentence from
    # delaying speech indefinitely.
    if len(buffer) >= 180:
        split_at = buffer.rfind(" ", 80, 180)

        if split_at > 0:
            return [buffer[:split_at]], buffer[split_at + 1:]

    return [], buffer


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Message cannot be empty."
        )

    session_id = request.session_id or uuid4()
    sid = str(session_id)

    language = (
        detect_language(message)
        if request.language == "auto"
        else request.language
    )

    async def events():
        async with chat_lock:

            if (
                request.session_id is not None
                and not conversation_manager.exists(sid)
            ):
                yield encode_event(
                    "error",
                    message="Conversation not found or expired."
                )
                return

            history = conversation_manager.get_history(sid)

            prompt = (
                RIA_SYSTEM_PROMPT
                + "\nLANGUAGE INSTRUCTIONS:\n"
                + get_language_instruction(language)
                + "\nSTYLE EXAMPLES:\n"
                + LANGUAGE_EXAMPLES[language]
                + "\nVOICE RESPONSE:\n"
                + "Use natural spoken sentences. "
                + "Avoid Markdown formatting and speaker labels."
            )

            messages = [
                {"role": "system", "content": prompt},
                *history,
                {"role": "user", "content": message}
            ]

            yield encode_event(
                "meta",
                session_id=sid,
                language=language,
                model=OLLAMA_MODEL
            )

            raw_parts = []
            buffer = ""

            try:
                async for piece in stream_reply(messages):
                    raw_parts.append(piece)
                    buffer += piece

                    sentences, buffer = get_ready_sentences(
                        buffer
                    )

                    for sentence in sentences:
                        sentence = sentence.strip()

                        if not sentence:
                            continue

                        if language == "tanglish":
                            sentence = tamil_to_tanglish(
                                sentence
                            )

                        yield encode_event(
                            "sentence",
                            text=sentence
                        )

                if buffer.strip():
                    final_sentence = buffer.strip()

                    if language == "tanglish":
                        final_sentence = tamil_to_tanglish(
                            final_sentence
                        )

                    yield encode_event(
                        "sentence",
                        text=final_sentence
                    )

                raw_reply = "".join(raw_parts).strip()

                if not raw_reply:
                    raise LLMError("Model returned no text.")

                reply = (
                    tamil_to_tanglish(raw_reply)
                    if language == "tanglish"
                    else raw_reply
                )

                valid = validate_response(reply, language)

                conversation_manager.save_exchange(
                    sid,
                    message,
                    reply
                )

                yield encode_event(
                    "done",
                    session_id=sid,
                    language_valid=valid
                )

            except LLMError as exc:
                yield encode_event(
                    "error",
                    message=str(exc)
                )

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff"
        }
    )
