from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import NoResultFound

from backend.app.main import app
from backend.app.db.postgres import get_session
from backend.app.schemas.raw_events import RawEventRecord


def _make_record(status: str = "enqueued", **kwargs) -> RawEventRecord:
    now = datetime.now(timezone.utc)
    defaults = dict(
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
        enqueued_msg_id="1-0",
        error_reason=None,
        event_card_id=None,
        processed_at=None,
        raw_metadata={},
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    return RawEventRecord(**defaults)


@pytest.fixture()
def client():
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    app.dependency_overrides[get_session] = lambda: mock_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_RAW_ID = str(uuid.uuid4())
_CARD_ID = str(uuid.uuid4())


def test_patch_processed_saves_status_and_card_id(client):
    now = datetime.now(timezone.utc)
    expected = _make_record(
        id=_RAW_ID,
        status="processed",
        event_card_id=_CARD_ID,
        processed_at=now,
    )
    with patch(
        "backend.app.api.admin.raw_event_service.update_status",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_svc:
        resp = client.patch(
            f"/api/admin/raw-events/{_RAW_ID}/status",
            json={"status": "processed", "event_card_id": _CARD_ID},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "processed"
    assert body["event_card_id"] == _CARD_ID
    mock_svc.assert_awaited_once()


def test_patch_failed_saves_error_reason(client):
    long_reason = "x" * 600
    expected = _make_record(
        id=_RAW_ID,
        status="failed",
        error_reason=long_reason[:500],
    )
    with patch(
        "backend.app.api.admin.raw_event_service.update_status",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        resp = client.patch(
            f"/api/admin/raw-events/{_RAW_ID}/status",
            json={"status": "failed", "error_reason": long_reason},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error_reason"] == long_reason[:500]


def test_patch_unknown_raw_event_returns_404(client):
    with patch(
        "backend.app.api.admin.raw_event_service.update_status",
        new_callable=AsyncMock,
        side_effect=NoResultFound("not found"),
    ):
        resp = client.patch(
            f"/api/admin/raw-events/{_RAW_ID}/status",
            json={"status": "processed"},
        )

    assert resp.status_code == 404


def test_get_existing_raw_event_returns_200(client):
    expected = _make_record(id=_RAW_ID)
    with patch(
        "backend.app.api.admin.raw_event_service.get_raw_event",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        resp = client.get(f"/api/admin/raw-events/{_RAW_ID}")

    assert resp.status_code == 200
    assert resp.json()["id"] == _RAW_ID


def test_get_nonexistent_raw_event_returns_404(client):
    with patch(
        "backend.app.api.admin.raw_event_service.get_raw_event",
        new_callable=AsyncMock,
        side_effect=NoResultFound("not found"),
    ):
        resp = client.get(f"/api/admin/raw-events/{_RAW_ID}")

    assert resp.status_code == 404
