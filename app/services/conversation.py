
from app.core.config import (
    MAX_HISTORY_MESSAGES,
    MAX_SESSIONS
)


class ConversationManager:
    def __init__(self):
        self.sessions = {}

    def get_history(self, session_id: str) -> list[dict]:
        return list(self.sessions.get(session_id, []))

    def exists(self, session_id: str) -> bool:
        return session_id in self.sessions

    def save_exchange(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str
    ) -> None:
        history = self.sessions.get(session_id, [])

        history.append({
            "role": "user",
            "content": user_message
        })

        history.append({
            "role": "assistant",
            "content": assistant_reply
        })

        self.sessions[session_id] = history[-MAX_HISTORY_MESSAGES:]

        # Keep the number of sessions bounded.
        while len(self.sessions) > MAX_SESSIONS:
            oldest_id = next(iter(self.sessions))
            self.sessions.pop(oldest_id)

    def clear(self, session_id: str) -> bool:
        return self.sessions.pop(session_id, None) is not None


conversation_manager = ConversationManager()
