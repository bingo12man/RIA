
import json
import os
import re
import threading
import urllib.error
import urllib.request
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# ============================================================
# RIA-1 — MODULE 5.4
# Conversational Intelligence + Dynamic Response Length
# ============================================================

app = FastAPI(title="RIA-1 Conversational Engine")

MODEL = os.getenv("RIA_MODEL", "qwen3.5:4b")
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

# Last 10 messages = 5 user-assistant exchanges.
MAX_HISTORY = 10


# ============================================================
# RIA PERSONALITY
# ============================================================

RIA_PERSONALITY = """
You are Ria, a warm, intelligent and friendly AI desk companion.

PERSONALITY:
- Be natural, thoughtful, calm and gently playful.
- Speak like a friendly companion, not a lecturer.
- Avoid exaggerated praise and repetitive reassurance.
- Never invent personal details or events.

RESPONSE STYLE:
- Be concise by default, usually 1-3 short sentences.
- Give the answer first.
- Avoid unnecessary introductions, metaphors and repetition.
- Expand when the user requests detail or the question needs it.
- Follow specific instructions about length and format.
- Complete every explanation and sentence naturally.
- Do not end every reply with a question.

CONVERSATION:
- Use the provided conversation history to understand context.
- Understand follow-up questions such as "it", "them", or "that".
- Do not pretend to remember information outside the history.
- Ask for clarification if something is unclear.

SAFETY:
- Do not claim to perform actions you did not perform.
- No external tools are available in this version.
- Never claim to send messages, set reminders, or change files.
- Respond in English for now.
"""


# ============================================================
# SESSION STORAGE
# ============================================================

# Development-only, in-memory storage.
# Sessions disappear when FastAPI restarts.
sessions = {}
session_locks = {}
storage_lock = threading.Lock()


def get_session_lock(session_id: str):
    with storage_lock:
        if session_id not in session_locks:
            session_locks[session_id] = threading.Lock()

        return session_locks[session_id]


# ============================================================
# LANGUAGE ROUTING
# ============================================================

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


def detect_language(text: str) -> str:
    if TAMIL_SCRIPT.search(text):
        return "tamil_script"

    tokens = set(re.findall(r"[a-z]+", text.lower()))

    if tokens.intersection(TANGLISH_HINTS):
        return "possible_tanglish"

    return "english_or_unknown"


# ============================================================
# DYNAMIC RESPONSE LENGTH
# ============================================================

def response_style(message: str):
    text = message.lower()

    detailed_phrases = (
        "in detail",
        "detailed",
        "step by step",
        "step-by-step",
        "explain fully",
        "don't keep it short",
        "do not keep it short",
        "comprehensive",
        "in depth",
        "in-depth",
        "elaborate",
        "thoroughly",
    )

    brief_phrases = (
        "briefly",
        "keep it short",
        "short answer",
        "in one sentence",
        "one line",
        "quick answer",
        "be concise",
        "summarize briefly",
    )

    # Explicit brevity takes priority.
    if any(phrase in text for phrase in brief_phrases):
        return (
            "brief",
            (
                "The user wants a brief answer. "
                "Respond directly in 1-2 short sentences. "
                "Avoid unnecessary detail, but answer fully."
            ),
            200,
        )

    if any(phrase in text for phrase in detailed_phrases):
        return (
            "detailed",
            (
                "The user explicitly requested a detailed answer. "
                "Provide a complete explanation rather than a summary. "
                "Cover each requested topic with clear examples. "
                "Use sections or numbered steps when helpful. "
                "Explain important differences and practical uses. "
                "Do not stop after a short introductory paragraph."
            ),
            1100,
        )

    return (
        "normal",
        (
            "Respond naturally and concisely. "
            "Usually use 1-3 short sentences. "
            "Give useful advice directly. "
            "Expand only as needed to answer the request fully."
        ),
        400,
    )


# ============================================================
# REQUEST AND RESPONSE MODELS
# ============================================================

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(
        default=None,
        max_length=128,
    )


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    language_route: str
    response_style: str
    history_messages: int
    model: str


# ============================================================
# OLLAMA INFERENCE
# ============================================================

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
            request,
            timeout=240,
        ) as response:
            data = json.load(response)

        reply = data.get("message", {}).get(
            "content", ""
        ).strip()

        if not reply:
            raise RuntimeError(
                "Ollama returned an empty response."
            )

        return reply

    except (
        urllib.error.URLError,
        TimeoutError,
        RuntimeError,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama error: {error}",
        ) from error


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "assistant": "RIA-1",
        "module": "5.4",
        "model": MODEL,
        "max_history": MAX_HISTORY,
    }


# ============================================================
# CHAT ENDPOINT
# ============================================================

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
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
                "I can see you're writing in Tamil. "
                "Could you say that in English for now? "
                "My Tamil understanding is still being tested."
            )

            style_name = "clarification"

        elif route == "possible_tanglish":
            reply = (
                "I think you're using Tanglish. "
                "Could you say that in English for now? "
                "I don't want to misunderstand you."
            )

            style_name = "clarification"

        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        RIA_PERSONALITY
                        + "\n\nCURRENT RESPONSE INSTRUCTION:\n"
                        + style_instruction
                    ),
                },
                *history,
                {
                    "role": "user",
                    "content": message,
                },
            ]

            reply = ask_ollama(
                messages,
                max_tokens=max_tokens,
            )

        # Save both messages after a successful response.
        updated_history = history + [
            {
                "role": "user",
                "content": message,
            },
            {
                "role": "assistant",
                "content": reply,
            },
        ]

        sessions[session_id] = updated_history[
            -MAX_HISTORY:
        ]

        return ChatResponse(
            reply=reply,
            session_id=session_id,
            language_route=route,
            response_style=style_name,
            history_messages=len(sessions[session_id]),
            model=MODEL,
        )


# ============================================================
# VIEW SESSION
# ============================================================

@app.get("/session/{session_id}")
def get_session(session_id: str):
    with get_session_lock(session_id):
        if session_id not in sessions:
            raise HTTPException(
                status_code=404,
                detail="Session not found.",
            )

        return {
            "session_id": session_id,
            "messages": list(sessions[session_id]),
        }


# ============================================================
# DELETE SESSION
# ============================================================

@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    with get_session_lock(session_id):
        existed = session_id in sessions

        sessions.pop(session_id, None)

        return {
            "deleted": existed,
            "session_id": session_id,
        }
