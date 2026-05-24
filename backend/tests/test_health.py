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
        patch("backend.app.db.opensearch.ping", return_value=True),
    ):
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body.get("version") == "0.1.0"
    assert "redis" in body
    assert "milvus" in body
    assert body.get("postgres") == "ok"
    assert "components" in body
    assert body["components"]["redis"] == "ok"
    assert body["components"]["postgres"] == "ok"
    assert body["components"]["opensearch"] == "ok"


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
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch(
            "backend.app.api.themes.event_service.count_by_theme",
            new_callable=AsyncMock,
            return_value={"geopolitics": 3, "economics": 1},
        ):
            resp = client.get("/api/themes")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 0
    assert "name" in body[0]
    assert body[0]["event_count"] >= 0


def test_sectors_list():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch(
            "backend.app.api.sectors.event_service.count_by_sector",
            new_callable=AsyncMock,
            return_value={"energy": 2},
        ):
            resp = client.get("/api/sectors")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 0
    assert "name" in body[0]
    assert body[0]["event_count"] >= 0


def test_ai_reply_mock():
    resp = client.post(
        "/api/ai-replies/request",
        json={"event_id": "test-id", "prompt_hint": "summarize"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "reply" in body
    assert "[mock]" in body["reply"]
