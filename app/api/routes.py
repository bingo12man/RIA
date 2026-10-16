
import asyncio
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services.transliteration import tamil_to_tanglish

from app.core.config import (
    APP_NAME,
    APP_VERSION,
    OLLAMA_MODEL,
    MAX_RESPONSE_RETRIES
)
from app.core.personality import RIA_SYSTEM_PROMPT
from app.core.language_examples import LANGUAGE_EXAMPLES
from app.services.language import (
    detect_language,
    get_language_instruction,
    validate_response
)
from app.services.conversation import conversation_manager
from app.services.llm import generate_reply, LLMError


router = APIRouter()
chat_lock = asyncio.Lock()

LanguageChoice = Literal[
    "auto", "english", "tamil", "tanglish"
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    language: LanguageChoice = "auto"


class ChatResponse(BaseModel):
    reply: str
    session_id: UUID
    model: str
    language: str
    language_valid: bool


@router.get("/")
def root():
    return {
        "name": APP_NAME,
        "message": "RIA backend is running"
    }


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ria-backend",
        "version": APP_VERSION
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Message cannot be empty."
        )

    async with chat_lock:
        session_id = request.session_id or uuid4()
        sid = str(session_id)

        if (
            request.session_id is not None
            and not conversation_manager.exists(sid)
        ):
            raise HTTPException(
                status_code=404,
                detail="Conversation not found or expired."
            )

        language = (
            detect_language(message)
            if request.language == "auto"
            else request.language
        )

        history = conversation_manager.get_history(sid)

        system_prompt = (
            RIA_SYSTEM_PROMPT
            + "\nLANGUAGE INSTRUCTIONS:\n"
            + get_language_instruction(language)
            + "\nSTYLE EXAMPLES:\n"
            + LANGUAGE_EXAMPLES[language]
        )

        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": message}
        ]

        try:
            reply = await generate_reply(messages)

            if language == "tanglish":
                reply = tamil_to_tanglish(reply)

            valid = validate_response(reply, language)

            valid = validate_response(reply, language)

            for _ in range(MAX_RESPONSE_RETRIES):
                if valid:
                    break

                retry_messages = [
                    *messages,
                    {"role": "assistant", "content": reply},
                    {
                        "role": "user",
                        "content": (
                            "Please answer the original question "
                            "again. Follow the required language "
                            "and script exactly. Preserve meaning."
                        )
                    }
                ]

                reply = await generate_reply(retry_messages)
                if language == "tanglish":
                    reply = tamil_to_tanglish(reply)

                valid = validate_response(reply, language)
                valid = validate_response(reply, language)

        except LLMError as exc:
            raise HTTPException(
                status_code=503,
                detail=str(exc)
            ) from exc

        conversation_manager.save_exchange(
            sid,
            message,
            reply
        )

        return ChatResponse(
            reply=reply,
            session_id=session_id,
            model=OLLAMA_MODEL,
            language=language,
            language_valid=valid
        )


@router.delete("/chat/{session_id}")
async def delete_conversation(session_id: UUID):
    async with chat_lock:
        deleted = conversation_manager.clear(str(session_id))

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    return {"status": "deleted"}
