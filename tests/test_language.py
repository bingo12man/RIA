
from fastapi.testclient import TestClient

from app.main import app
from app.api import routes
from app.services.language import (
    detect_language,
    get_language_instruction,
    validate_response,
)
from app.services.tone import detect_tone


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


def test_tanglish_conversational_detection():
    assert detect_language(
        "Enakku romba bore adikkudhu"
    ) == "tanglish"


def test_tanglish_format_valid():
    assert validate_response(
        "Aama, namma pesalaam!",
        "tanglish"
    ) is True


def test_tanglish_script_invalid():
    assert validate_response(
        "நம்ம பேசலாம்",
        "tanglish"
    ) is False


def test_tamil_format_valid():
    assert validate_response(
        "வணக்கம், எப்படி இருக்கீங்க?",
        "tamil"
    ) is True


def test_tamil_format_invalid():
    assert validate_response(
        "Vanakkam, epdi irukka?",
        "tamil"
    ) is False


def test_english_rejects_tamil_script():
    assert validate_response(
        "வணக்கம்",
        "english"
    ) is False


def test_empty_response_invalid():
    for language in ("english", "tamil", "tanglish"):
        assert validate_response(
            "   ",
            language
        ) is False


def test_language_instruction_exists():
    for language in ("english", "tamil", "tanglish"):
        instruction = get_language_instruction(language)
        assert isinstance(instruction, str)
        assert instruction.strip()


def test_emotional_tone_detection():
    assert detect_tone(
        "I'm feeling lonely tonight"
    ) == "lonely_vulnerable"

    assert detect_tone(
        "I finally got good news!"
    ) == "happy_excited"

    assert detect_tone(
        "I don't understand this concept"
    ) == "confused_learning"


def test_explicit_language_override(monkeypatch):
    async def fake_generate(messages):
        system = messages[0]["content"]

        assert "LANGUAGE INSTRUCTIONS" in system
        assert "CURRENT EMOTIONAL CONTEXT" in system

        return "Aama, namma pesalaam!"

    monkeypatch.setattr(
        routes,
        "generate_reply",
        fake_generate
    )

    response = client.post(
        "/chat",
        json={
            "message": "Hello Ria",
            "language": "tanglish"
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["language"] == "tanglish"
    assert data["language_valid"] is True
    assert data["reply"] == "Aama, namma pesalaam!"


def test_direct_tanglish_no_conversion(monkeypatch):
    calls = []

    async def fake_generate(messages):
        calls.append(messages)
        return "Aiyo, enna aachu? Sollu, kekkuren."

    monkeypatch.setattr(
        routes,
        "generate_reply",
        fake_generate
    )

    response = client.post(
        "/chat",
        json={
            "message": "Enakku romba kashtama irukku",
            "language": "tanglish"
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["language_valid"] is True
    assert data["reply"] == (
        "Aiyo, enna aachu? Sollu, kekkuren."
    )
    assert len(calls) == 1


def test_tanglish_retry_wrong_script(monkeypatch):
    calls = []

    async def fake_generate(messages):
        calls.append(messages)

        if len(calls) == 1:
            return "வணக்கம்"

        return "Vanakkam! Epdi irukka?"

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

    assert data["reply"] == "Vanakkam! Epdi irukka?"
    assert data["language_valid"] is True
    assert len(calls) == 2


def test_retry_exhausted_reports_invalid(monkeypatch):
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

    assert data["language_valid"] is False
    assert data["reply"] == "வணக்கம்"
    assert len(calls) == routes.MAX_RESPONSE_RETRIES + 1


def test_invalid_language():
    response = client.post(
        "/chat",
        json={
            "message": "Hello",
            "language": "french"
        }
    )

    assert response.status_code == 422
