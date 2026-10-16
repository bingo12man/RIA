
from fastapi.testclient import TestClient

from app.main import app
from app.api import routes
from app.services.language import (
    detect_language,
    validate_response
)


client = TestClient(app)


def test_english_detection():
    assert detect_language(
        "Explain neural networks"
    ) == "english"


def test_tamil_detection():
    assert detect_language(
        "எனக்கு தமிழ் தெரியும்"
    ) == "tamil"


def test_tanglish_detection():
    assert detect_language(
        "Unakku Tamil theriyuma?"
    ) == "tanglish"


def test_tanglish_response_validation():
    assert validate_response(
        "Aama, namma pesalam!",
        "tanglish"
    ) is True

    assert validate_response(
        "நம்ம பேசலாம்",
        "tanglish"
    ) is False


def test_explicit_language_override(monkeypatch):
    async def fake_generate(messages):
        assert "LANGUAGE INSTRUCTIONS" in messages[0]["content"]
        return "Aama, namma pesalam!"

    monkeypatch.setattr(
        routes,
        "generate_reply",
        fake_generate
    )

    response = client.post(
        "/chat",
        json={
            "message": "Hello RIA",
            "language": "tanglish"
        }
    )

    assert response.status_code == 200
    assert response.json()["language"] == "tanglish"
    assert response.json()["language_valid"] is True



def test_tanglish_conversion(monkeypatch):
    calls = []

    async def fake_generate(messages):
        calls.append(messages)
        return "வணக்கம்"

    monkeypatch.setattr(
        routes,
        "generate_reply",
        fake_generate
    )

    response = client.post(
        "/chat",
        json={
            "message": "Unakku Tamil theriyuma?",
            "language": "tanglish"
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["language"] == "tanglish"
    assert data["language_valid"] is True

    # Tamil script must be converted to Latin characters.
    assert not any(
        "\u0B80" <= char <= "\u0BFF"
        for char in data["reply"]
    )

    # Successful conversion requires only one model call.
    assert len(calls) == 1



def test_invalid_language():
    response = client.post(
        "/chat",
        json={
            "message": "Hello",
            "language": "french"
        }
    )

    assert response.status_code == 422
