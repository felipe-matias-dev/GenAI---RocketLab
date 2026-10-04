import pytest
from fastapi.testclient import TestClient

from app import main
from app.orchestrator import AllModelsFailedError


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_returns_orchestrator_result(client, monkeypatch):
    fake_result = {
        "answer": "Resposta de teste.",
        "sql_used": ["SELECT 1"],
        "data": [{"n": 1}],
        "model_used": "model-a:free",
    }
    monkeypatch.setattr(main._orchestrator, "ask", lambda question, session_id=None: fake_result)

    response = client.post("/ask", json={"question": "pergunta de teste"})

    assert response.status_code == 200
    assert response.json() == fake_result


def test_ask_response_includes_new_fields_when_present(client, monkeypatch):
    fake_result = {
        "answer": "Resposta de teste.",
        "sql_used": ["SELECT 1"],
        "data": [{"n": 1}],
        "model_used": "model-a:free",
        "confidence": 0.85,
        "reasoning": "porque a query retornou dados consistentes",
        "schema_link": {"tables": ["dim_movies"], "columns": [], "reasoning": "r"},
    }
    monkeypatch.setattr(main._orchestrator, "ask", lambda question, session_id=None: fake_result)

    response = client.post("/ask", json={"question": "pergunta de teste"})

    assert response.status_code == 200
    assert response.json() == fake_result


def test_ask_returns_503_when_all_models_fail(client, monkeypatch):
    def raise_failure(question, session_id=None):
        raise AllModelsFailedError("nenhum modelo respondeu")

    monkeypatch.setattr(main._orchestrator, "ask", raise_failure)

    response = client.post("/ask", json={"question": "pergunta de teste"})

    assert response.status_code == 503


def test_static_ui_served_at_root(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "<html" in response.text.lower()
