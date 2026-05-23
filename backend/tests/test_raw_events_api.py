from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.postgres import get_session
from backend.app.schemas.raw_events import RawEventCreateResponse, RawEventRecord


def _make_record(is_duplicate: bool = False) -> RawEventRecord:
    now = datetime.now(timezone.utc)
    return RawEventRecord(
        id=str(uuid.uuid4()),
        source_type="rss",
        source_name="test_feed",
        external_id="guid-001",
        url="https://example.com/article/1",
        title="Test Article",
        raw_text="Some summary text.",
        published_at=now,
        collected_at=now,
        content_hash="a" * 64,
        theme_hint="test",
        status="enqueued" if not is_duplicate else "collected",
        enqueued_msg_id="1-0" if not is_duplicate else None,
        error_reason=None,
        raw_metadata={"rss": {"feed_title": "Test Feed", "guid": "guid-001", "tags": []}},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture()
def client(mock_session):
    app.dependency_overrides[get_session] = lambda: mock_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_PAYLOAD = {
    "source_type": "rss",
    "source_name": "test_feed",
    "external_id": "guid-001",
    "url": "https://example.com/article/1",
    "title": "Test Article",
    "raw_text": "Some summary text.",
    "published_at": "2026-05-23T08:00:00+00:00",
    "content_hash": "a" * 64,
    "theme_hint": "test",
    "raw_metadata": {"rss": {"feed_title": "Test Feed", "guid": "guid-001", "tags": []}},
}


def test_create_raw_event_insert_and_enqueue(client):
    response_obj = RawEventCreateResponse(
        record=_make_record(is_duplicate=False),
        is_duplicate=False,
        enqueued_msg_id="1-0",
    )
    with patch("backend.app.api.admin.raw_event_service.create_raw_event", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = response_obj
        resp = client.post("/api/admin/raw-events", json=_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_duplicate"] is False
    assert body["enqueued_msg_id"] == "1-0"
    assert body["record"]["source_name"] == "test_feed"


def test_create_raw_event_duplicate_no_enqueue(client):
    response_obj = RawEventCreateResponse(
        record=_make_record(is_duplicate=True),
        is_duplicate=True,
        enqueued_msg_id=None,
    )
    with patch("backend.app.api.admin.raw_event_service.create_raw_event", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = response_obj
        resp = client.post("/api/admin/raw-events", json=_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_duplicate"] is True
    assert body["enqueued_msg_id"] is None


def test_create_raw_event_xadd_failure_returns_null_msg_id(client):
    response_obj = RawEventCreateResponse(
        record=_make_record(is_duplicate=False),
        is_duplicate=False,
        enqueued_msg_id=None,
    )
    with patch("backend.app.api.admin.raw_event_service.create_raw_event", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = response_obj
        resp = client.post("/api/admin/raw-events", json=_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_duplicate"] is False
    assert body["enqueued_msg_id"] is None


def test_create_raw_event_minimal_payload(client):
    minimal = {
        "source_name": "test_feed",
        "url": "https://example.com/article/2",
        "content_hash": "b" * 64,
    }
    now = datetime.now(timezone.utc)
    record = RawEventRecord(
        id=str(uuid.uuid4()),
        source_type="rss",
        source_name="test_feed",
        external_id=None,
        url="https://example.com/article/2",
        title=None,
        raw_text="",
        published_at=None,
        collected_at=now,
        content_hash="b" * 64,
        theme_hint=None,
        status="enqueued",
        enqueued_msg_id="2-0",
        error_reason=None,
        raw_metadata={},
        created_at=now,
        updated_at=now,
    )
    response_obj = RawEventCreateResponse(record=record, is_duplicate=False, enqueued_msg_id="2-0")
    with patch("backend.app.api.admin.raw_event_service.create_raw_event", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = response_obj
        resp = client.post("/api/admin/raw-events", json=minimal)

    assert resp.status_code == 200
    body = resp.json()
    assert body["record"]["external_id"] is None
    assert body["record"]["title"] is None


def test_create_raw_event_xadd_failure_sets_status_failed(client):
    now = datetime.now(timezone.utc)
    failed_record = RawEventRecord(
        id=str(uuid.uuid4()),
        source_type="rss",
        source_name="test_feed",
        external_id=None,
        url="https://example.com/article/3",
        title=None,
        raw_text="body",
        published_at=None,
        collected_at=now,
        content_hash="c" * 64,
        theme_hint=None,
        status="failed",
        enqueued_msg_id=None,
        error_reason="xadd_failed: Redis connection refused",
        raw_metadata={},
        created_at=now,
        updated_at=now,
    )
    response_obj = RawEventCreateResponse(record=failed_record, is_duplicate=False, enqueued_msg_id=None)
    with patch("backend.app.api.admin.raw_event_service.create_raw_event", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = response_obj
        resp = client.post(
            "/api/admin/raw-events",
            json={"source_name": "test_feed", "url": "https://example.com/article/3", "content_hash": "c" * 64},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["record"]["status"] == "failed"
    assert body["record"]["error_reason"].startswith("xadd_failed:")
    assert body["enqueued_msg_id"] is None


def test_collect_rss_once_calls_rss_collector_run(client):
    summary = {"sources": 3, "items_seen": 10, "items_enqueued": 8, "duplicates": 2, "errors": 0, "per_source": []}
    with patch("workers.collectors.rss_collector.run", return_value=summary):
        resp = client.post("/api/admin/collect-rss-once")

    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"] == 3
    assert body["items_enqueued"] == 8
