from __future__ import annotations

"""P0 하드닝: 공개 /api/events 목록이 published 카드만 노출하는지(hold 차단)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.db.postgres import get_session
from backend.app.main import app
from backend.app.schemas.events import FinalEventCard

client = TestClient(app)


async def _fake_session():
    yield AsyncMock()


def _card(status: str) -> FinalEventCard:
    return FinalEventCard(
        id="11111111-1111-1111-1111-111111111111",
        title="t", summary="s", theme="general",
        status=status, created_at=datetime.now(timezone.utc),
    )


def test_list_events_requests_published_only():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch(
            "backend.app.services.event_service.list_events",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_list:
            resp = client.get("/api/events")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    mock_list.assert_awaited_once()
    # 라우트는 status="published"로 호출해야 한다 — hold 카드 노출 차단.
    assert mock_list.await_args.kwargs.get("status") == "published"


def test_get_event_hides_hold_card():
    # 단건조회도 hold 카드는 404 (목록 필터 우회 차단, R-MockCard)
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch(
            "backend.app.services.event_service.get_event",
            new_callable=AsyncMock,
            return_value=_card("hold"),
        ):
            resp = client.get("/api/events/11111111-1111-1111-1111-111111111111")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 404


def test_get_event_returns_published_card():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch(
            "backend.app.services.event_service.get_event",
            new_callable=AsyncMock,
            return_value=_card("published"),
        ):
            resp = client.get("/api/events/11111111-1111-1111-1111-111111111111")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"
