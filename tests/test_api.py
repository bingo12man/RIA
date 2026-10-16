from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "RIA Personal AI Companion"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ria-backend", "version": "0.1.0"}


def test_unknown_route():
    assert client.get("/no-such-route").status_code == 404


def test_docs_disabled():
    assert client.get("/docs").status_code == 404
