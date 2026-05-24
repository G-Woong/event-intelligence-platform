from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import NoResultFound

from backend.app.main import app
from backend.app.core.security import require_admin_token
from backend.app.db.postgres import get_session
from backend.app.schemas.raw_events import RawEventRecord


def _make_record(status: str = "enqueued", requeue_count: int = 1) -> RawEventRecord:
    now = datetime.now(timezone.utc)
    return RawEventRecord(
        id=str(uuid.uuid4()),
        source_type="rss",
        source_name="test_feed",
        external_id=None,
        url="https://example.com/article/1",
        title="Test",
        raw_text="body",
        published_at=now,
        collected_at=now,
        content_hash="a" * 64,
        theme_hint=None,
        status=status,
        enqueued_msg_id="99-0",
        error_reason=None,
        event_card_id=None,
        processed_at=None,
        raw_metadata={"requeue_count": requeue_count},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def client():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_admin_token] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_RAW_ID = str(uuid.uuid4())


def test_requeue_success_returns_200(client):
    record = _make_record(status="enqueued", requeue_count=1)
    with patch(
        "backend.app.api.admin.raw_event_service.requeue_raw_event",
        new_callable=AsyncMock,
        return_value=(record, "99-0", 1),
    ):
        resp = client.post(f"/api/admin/raw-events/{_RAW_ID}/requeue", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["enqueued_msg_id"] == "99-0"
    assert body["requeue_count"] == 1
    assert body["record"]["status"] == "enqueued"


def test_requeue_not_found_returns_404(client):
    with patch(
        "backend.app.api.admin.raw_event_service.requeue_raw_event",
        new_callable=AsyncMock,
        side_effect=NoResultFound("not found"),
    ):
        resp = client.post(f"/api/admin/raw-events/{_RAW_ID}/requeue", json={})

    assert resp.status_code == 404


def test_requeue_processed_without_force_returns_409(client):
    with patch(
        "backend.app.api.admin.raw_event_service.requeue_raw_event",
        new_callable=AsyncMock,
        side_effect=ValueError("requeue refused: row already processed; pass force=true to override"),
    ):
        resp = client.post(f"/api/admin/raw-events/{_RAW_ID}/requeue", json={"force": False})

    assert resp.status_code == 409
    assert "already processed" in resp.json()["detail"]


def test_requeue_requires_auth():
    """token 설정 시 헤더 없으면 401."""
    app.dependency_overrides.clear()
    with patch("backend.app.core.security.settings") as mock_settings:
        mock_settings.ADMIN_API_TOKEN = "secret"
        with TestClient(app) as c:
            resp = c.post(f"/api/admin/raw-events/{_RAW_ID}/requeue", json={})
    assert resp.status_code == 401
