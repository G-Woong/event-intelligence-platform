from fastapi.testclient import TestClient
from unittest.mock import patch
from backend.app.main import app

client = TestClient(app)


def test_health_returns_ok():
    with patch("backend.app.db.redis.ping", return_value=True), \
         patch("backend.app.db.milvus.is_connected", return_value=False):
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "redis" in body
    assert "milvus" in body


def test_events_empty_list():
    resp = client.get("/api/events")
    assert resp.status_code == 200
    assert resp.json() == []


def test_event_not_found():
    resp = client.get("/api/events/nonexistent-id")
    assert resp.status_code == 404


def test_themes_list():
    resp = client.get("/api/themes")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_sectors_list():
    resp = client.get("/api/sectors")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_ai_reply_mock():
    resp = client.post(
        "/api/ai-replies/request",
        json={"event_id": "test-id", "prompt_hint": "summarize"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "reply" in body
    assert "[mock]" in body["reply"]
