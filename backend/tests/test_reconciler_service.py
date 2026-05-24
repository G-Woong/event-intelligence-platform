from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.schemas.raw_events import RawEventRecord
from backend.app.services import reconciler_service


def _make_record(status: str = "enqueued", delta_seconds: int = 700, **kwargs) -> RawEventRecord:
    now = datetime.now(timezone.utc)
    updated_at = now - timedelta(seconds=delta_seconds)
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
        updated_at=updated_at,
    )
    defaults.update(kwargs)
    return RawEventRecord(**defaults)


@pytest.mark.asyncio
async def test_list_stuck_enqueued_returns_threshold_rows():
    old_record = _make_record(status="enqueued", delta_seconds=700)

    with patch(
        "backend.app.services.reconciler_service.list_by_status_older_than",
        new_callable=AsyncMock,
        return_value=[old_record],
    ) as mock_list:
        session = AsyncMock()
        result = await reconciler_service.list_stuck_enqueued(session, before_seconds=600)

    assert len(result) == 1
    assert result[0].status == "enqueued"
    mock_list.assert_awaited_once_with(session, status="enqueued", before_seconds=600, limit=100)


@pytest.mark.asyncio
async def test_list_stuck_enqueued_respects_limit():
    records = [_make_record(status="enqueued") for _ in range(3)]

    with patch(
        "backend.app.services.reconciler_service.list_by_status_older_than",
        new_callable=AsyncMock,
        return_value=records[:2],
    ) as mock_list:
        session = AsyncMock()
        result = await reconciler_service.list_stuck_enqueued(session, before_seconds=600, limit=2)

    assert len(result) == 2
    mock_list.assert_awaited_once_with(session, status="enqueued", before_seconds=600, limit=2)


@pytest.mark.asyncio
async def test_list_stuck_enqueued_excludes_other_statuses():
    with patch(
        "backend.app.services.reconciler_service.list_by_status_older_than",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock_list:
        session = AsyncMock()
        result = await reconciler_service.list_stuck_enqueued(session)

    assert result == []
    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["status"] == "enqueued"


@pytest.mark.asyncio
async def test_mark_stuck_as_failed_dry_run_no_update():
    record = _make_record(status="enqueued")

    with patch(
        "backend.app.services.reconciler_service.list_stuck_enqueued",
        new_callable=AsyncMock,
        return_value=[record],
    ):
        session = AsyncMock()
        items, marked = await reconciler_service.mark_stuck_as_failed(
            session, dry_run=True
        )

    assert marked == 0
    assert len(items) == 1
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_stuck_as_failed_dry_run_false_marks_failed():
    record = _make_record(status="enqueued")

    with patch(
        "backend.app.services.reconciler_service.list_stuck_enqueued",
        new_callable=AsyncMock,
        return_value=[record],
    ):
        session = AsyncMock()
        items, marked = await reconciler_service.mark_stuck_as_failed(
            session, dry_run=False, error_reason="reconciler: stuck enqueued"
        )

    assert marked == 1
    assert len(items) == 1
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_stuck_as_failed_empty_result_returns_zero():
    with patch(
        "backend.app.services.reconciler_service.list_stuck_enqueued",
        new_callable=AsyncMock,
        return_value=[],
    ):
        session = AsyncMock()
        items, marked = await reconciler_service.mark_stuck_as_failed(
            session, dry_run=False
        )

    assert marked == 0
    assert items == []
    session.execute.assert_not_awaited()
