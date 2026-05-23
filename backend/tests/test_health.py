from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.db.postgres import get_session
from backend.app.main import app

client = TestClient(app)


async def _fake_session():
    yield AsyncMock()


def test_health_returns_ok():
    with (
        patch("backend.app.db.redis.ping", return_value=True),
        patch("backend.app.db.milvus.is_connected", return_value=False),
        patch("backend.app.db.postgres.ping", new_callable=AsyncMock, return_value=True),
    ):
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "redis" in body
    assert "milvus" in body
    assert body.get("postgres") == "ok"


def test_events_empty_list():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch(
            "backend.app.services.event_service.list_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get("/api/events")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 200
    assert resp.json() == []


def test_event_not_found():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch(
            "backend.app.services.event_service.get_event",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/api/events/nonexistent-id")
    finally:
        app.dependency_overrides.pop(get_session, None)
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
