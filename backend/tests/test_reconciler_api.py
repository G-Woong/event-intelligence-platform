from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.security import require_admin_token
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
    app.dependency_overrides[require_admin_token] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_reconcile_stuck_dry_run_returns_items_no_mark(client):
    stuck = _make_record(status="enqueued")

    with patch(
        "backend.app.api.admin.reconciler_service.mark_stuck_as_failed",
        new_callable=AsyncMock,
        return_value=([stuck], 0),
    ):
        resp = client.post(
            "/api/admin/raw-events/reconcile-stuck",
            json={"dry_run": True},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["marked_failed"] == 0
    assert body["stuck_count"] == 1
    assert len(body["items"]) == 1


def test_reconcile_stuck_dry_run_false_marks_failed(client):
    stuck = _make_record(status="enqueued")

    with patch(
        "backend.app.api.admin.reconciler_service.mark_stuck_as_failed",
        new_callable=AsyncMock,
        return_value=([stuck], 1),
    ):
        resp = client.post(
            "/api/admin/raw-events/reconcile-stuck",
            json={"dry_run": False},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is False
    assert body["marked_failed"] == 1
    assert body["stuck_count"] == 1


def test_list_raw_events_with_status_filter(client):
    enqueued = _make_record(status="enqueued")

    with patch(
        "backend.app.api.admin.raw_event_service.list_by_status_older_than",
        new_callable=AsyncMock,
        return_value=[enqueued],
    ) as mock_list:
        resp = client.get("/api/admin/raw-events?status=enqueued&before_seconds=600")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "enqueued"
    mock_list.assert_awaited_once()


def test_reconcile_stuck_empty_returns_zero(client):
    with patch(
        "backend.app.api.admin.reconciler_service.mark_stuck_as_failed",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        resp = client.post(
            "/api/admin/raw-events/reconcile-stuck",
            json={"dry_run": True},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["stuck_count"] == 0
    assert body["marked_failed"] == 0
    assert body["items"] == []
