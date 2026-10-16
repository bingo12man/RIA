
import os

APP_NAME = "RIA Personal AI Companion"
APP_VERSION = "0.2.1"

OLLAMA_URL = "http://127.0.0.1:11434"

OLLAMA_MODEL = os.getenv(
    "RIA_MODEL",
    "gemma3:4b"
)

MAX_HISTORY_MESSAGES = 10
MAX_SESSIONS = 50

MAX_RESPONSE_RETRIES = 1
