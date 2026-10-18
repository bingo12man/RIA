import json
import os
import re
import threading
import urllib.error
import urllib.request
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="RIA-1 Conversational Engine")

MODEL = os.getenv("RIA_MODEL", "qwen3.5:4b")
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MAX_HISTORY = 10

RIA_PERSONALITY = """
You are Ria, a warm, friendly AI desk companion.

Be conversational, calm, natural and gently playful.
Keep casual responses to 1-2 short sentences.
Answer simple questions concisely.
When asked for detail, explain the topic thoroughly.
Do not add unnecessary introductions or analogies.
Understand follow-up questions using conversation history.
Do not invent personal details or events.
Do not claim to have performed real-world actions.
Do not ask unnecessary follow-up questions.
Respond in English for now.
"""

sessions = {}
session_locks = {}
storage_lock = threading.Lock()

TANGLISH_HINTS = {
    "naan", "nee", "neenga", "enakku", "enoda",
    "ennoda", "enna", "innaiku", "nethu",
    "naalaiku", "naalaikku", "venum", "vendaam",
    "illa", "irukku", "irukken", "pannu",
    "pannala", "pannadha", "sollu", "solren",
    "theriyala", "romba", "konjam", "aagudhu",
    "aana", "kudu", "unga", "unkitta",
    "avan", "ava", "avanga", "epdi",
    "eppo", "enga", "yen",
}

TAMIL_SCRIPT = re.compile(r"[\u0B80-\u0BFF]")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=128)


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    language_route: str
    response_style: str
    history_messages: int
    model: str


def detect_language(text: str) -> str:
    if TAMIL_SCRIPT.search(text):
        return "tamil_script"

    tokens = set(re.findall(r"[a-z]+", text.lower()))

    if tokens.intersection(TANGLISH_HINTS):
        return "possible_tanglish"

    return "english_or_unknown"


def response_style(message: str):
    text = message.lower()

    brief_phrases = (
        "briefly",
        "keep it short",
        "short answer",
        "one sentence",
        "one line",
        "quick answer",
        "be concise",
    )

    detailed_phrases = (
        "in detail",
        "detailed",
        "step by step",
        "step-by-step",
        "explain fully",
        "don't keep it short",
        "comprehensive",
        "in depth",
        "elaborate",
        "thoroughly",
    )

    # Check detailed requests before brief ones.
    # "Don't keep it short" must not be treated as brief.
    if any(phrase in text for phrase in detailed_phrases):
        return (
            "detailed",
            "Provide a complete, structured explanation with "
            "examples and practical details. Do not be overly brief.",
            1100,
        )

    if any(phrase in text for phrase in brief_phrases):
        return (
            "brief",
            "Reply directly in 1-2 short sentences.",
            200,
        )

    return (
        "normal",
        "Reply naturally and concisely in 1-3 sentences. "
        "Expand only when necessary.",
        400,
    )


def ask_ollama(messages: list, max_tokens: int = 400) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.5,
            "num_ctx": 4096,
            "num_predict": max_tokens,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=240
        ) as response:
            data = json.load(response)

        reply = data.get("message", {}).get(
            "content", ""
        ).strip()

        if not reply:
            raise RuntimeError("Ollama returned an empty reply")

        return reply

    except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama error: {error}",
        ) from error


def get_session_lock(session_id: str):
    with storage_lock:
        if session_id not in session_locks:
            session_locks[session_id] = threading.Lock()

        return session_locks[session_id]


@app.get("/health")
def health():
    return {
        "status": "ok",
        "assistant": "RIA-1",
        "module": "5.4",
        "model": MODEL,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    session_id = request.session_id or str(uuid4())

    with get_session_lock(session_id):
        history = sessions.get(session_id, [])
        route = detect_language(message)

        style_name, style_instruction, max_tokens = (
            response_style(message)
        )

        if route == "tamil_script":
            reply = (
                "My Tamil understanding is still being tested. "
                "Could you say that in English for now?"
            )
            style_name = "clarification"

        elif route == "possible_tanglish":
            reply = (
                "I think you're using Tanglish. "
                "Could you say that in English for now?"
            )
            style_name = "clarification"

        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        RIA_PERSONALITY
                        + "\n\nCURRENT RESPONSE STYLE:\n"
                        + style_instruction
                    ),
                },
                *history,
                {"role": "user", "content": message},
            ]

            reply = ask_ollama(
                messages,
                max_tokens=max_tokens,
            )

        updated_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ]

        sessions[session_id] = updated_history[-MAX_HISTORY:]

        return ChatResponse(
            reply=reply,
            session_id=session_id,
            language_route=route,
            response_style=style_name,
            history_messages=len(sessions[session_id]),
            model=MODEL,
        )


@app.get("/session/{session_id}")
def get_session(session_id: str):
    with get_session_lock(session_id):
        if session_id not in sessions:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        return {
            "session_id": session_id,
            "messages": list(sessions[session_id]),
        }


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    with get_session_lock(session_id):
        existed = session_id in sessions
        sessions.pop(session_id, None)

        return {
            "deleted": existed,
            "session_id": session_id,
        }
