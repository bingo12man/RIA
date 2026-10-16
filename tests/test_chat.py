
from fastapi.testclient import TestClient

from app.main import app
from app.api import routes
from app.services.conversation import ConversationManager


client = TestClient(app)


def test_conversation_history():
    manager = ConversationManager()

    manager.save_exchange("test-session", "Hello", "Hi!")

    history = manager.get_history("test-session")

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["content"] == "Hi!"


def test_history_limit():
    manager = ConversationManager()

    for i in range(8):
        manager.save_exchange(
            "test-session",
            f"Question {i}",
            f"Answer {i}"
        )

    history = manager.get_history("test-session")

    assert len(history) == 10
    assert history[0]["content"] == "Question 3"


def test_chat_endpoint(monkeypatch):
    async def fake_generate_reply(messages):
        assert messages[0]["role"] == "system"
        return "Vanakkam! I'm RIA."

    monkeypatch.setattr(
        routes,
        "generate_reply",
        fake_generate_reply
    )

    response = client.post(
        "/chat",
        json={"message": "Vanakkam RIA"}
    )

    assert response.status_code == 200

    data = response.json()
    assert data["reply"] == "Vanakkam! I'm RIA."
    assert data["session_id"]

    delete_response = client.delete(
        f"/chat/{data['session_id']}"
    )

    assert delete_response.status_code == 200


def test_empty_message():
    response = client.post(
        "/chat",
        json={"message": "   "}
    )

    assert response.status_code == 422


def test_unknown_session():
    response = client.post(
        "/chat",
        json={
            "message": "Hello",
            "session_id": "00000000-0000-4000-8000-000000000001"
        }
    )

    assert response.status_code == 404


def test_ollama_error(monkeypatch):
    from app.services.llm import LLMError

    async def fake_failure(messages):
        raise LLMError("Cannot connect to Ollama.")

    monkeypatch.setattr(
        routes,
        "generate_reply",
        fake_failure
    )

    response = client.post(
        "/chat",
        json={"message": "Hello"}
    )

    assert response.status_code == 503
