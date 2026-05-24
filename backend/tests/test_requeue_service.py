from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import NoResultFound

from backend.app.services.raw_event_service import requeue_raw_event
from backend.app.models.raw_event import RawEventORM


def _make_orm_row(status: str = "failed", requeue_count: int = 0) -> MagicMock:
    row = MagicMock(spec=RawEventORM)
    row.id = uuid.uuid4()
    row.source_type = "rss"
    row.source_name = "test_feed"
    row.external_id = "guid-001"
    row.url = "https://example.com/article/1"
    row.title = "Test"
    row.raw_text = "body"
    row.published_at = datetime.now(timezone.utc)
    row.collected_at = datetime.now(timezone.utc)
    row.content_hash = "a" * 64
    row.theme_hint = None
    row.status = status
    row.enqueued_msg_id = "1-0"
    row.error_reason = "some error"
    row.event_card_id = None
    row.processed_at = None
    row.raw_metadata = {"requeue_count": requeue_count} if requeue_count else {}
    row.created_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    return row


@pytest.mark.asyncio
async def test_failed_row_requeued_successfully():
    """status=failed → requeue → status=enqueued, requeue_count=1, error_reason cleared."""
    row = _make_orm_row(status="failed")
    refreshed = _make_orm_row(status="enqueued", requeue_count=1)
    refreshed.enqueued_msg_id = "99-0"
    refreshed.error_reason = None
    refreshed.raw_metadata = {"requeue_count": 1}

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=lambda: row),
        MagicMock(),
        MagicMock(scalar_one=lambda: refreshed),
    ])

    with patch("backend.app.services.raw_event_service.enqueue_raw_event", return_value="99-0"):
        record, msg_id, requeue_count = await requeue_raw_event(session, str(row.id))

    assert record.status == "enqueued"
    assert msg_id == "99-0"
    assert requeue_count == 1
    assert record.error_reason is None


@pytest.mark.asyncio
async def test_enqueued_row_requeued_updates_msg_id():
    """status=enqueued → requeue → enqueued_msg_id 갱신."""
    row = _make_orm_row(status="enqueued")
    refreshed = _make_orm_row(status="enqueued", requeue_count=1)
    refreshed.enqueued_msg_id = "200-0"
    refreshed.raw_metadata = {"requeue_count": 1}

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=lambda: row),
        MagicMock(),
        MagicMock(scalar_one=lambda: refreshed),
    ])

    with patch("backend.app.services.raw_event_service.enqueue_raw_event", return_value="200-0"):
        record, msg_id, requeue_count = await requeue_raw_event(session, str(row.id))

    assert record.enqueued_msg_id == "200-0"
    assert requeue_count == 1


@pytest.mark.asyncio
async def test_processed_row_raises_value_error_without_force():
    """status=processed + force=False → ValueError."""
    row = _make_orm_row(status="processed")

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: row))

    with pytest.raises(ValueError, match="already processed"):
        await requeue_raw_event(session, str(row.id), force=False)


@pytest.mark.asyncio
async def test_processed_row_force_true_requeues():
    """status=processed + force=True → requeue 성공, requeue_count 증가."""
    row = _make_orm_row(status="processed", requeue_count=1)
    refreshed = _make_orm_row(status="enqueued", requeue_count=2)
    refreshed.enqueued_msg_id = "300-0"
    refreshed.raw_metadata = {"requeue_count": 2}

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=lambda: row),
        MagicMock(),
        MagicMock(scalar_one=lambda: refreshed),
    ])

    with patch("backend.app.services.raw_event_service.enqueue_raw_event", return_value="300-0"):
        record, msg_id, requeue_count = await requeue_raw_event(session, str(row.id), force=True)

    assert record.status == "enqueued"
    assert requeue_count == 2


@pytest.mark.asyncio
async def test_not_found_raises_no_result_found():
    """존재하지 않는 raw_event_id → NoResultFound."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    with pytest.raises(NoResultFound):
        await requeue_raw_event(session, str(uuid.uuid4()))
