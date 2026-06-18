from __future__ import annotations

"""P0 하드닝 Phase 2: xadd_failed 행 자동 requeue (poison 한도 보호)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.schemas.raw_events import RawEventRecord
from backend.app.services import reconciler_service


def _rec(error_reason: str | None, requeue_count: int = 0, status: str = "failed") -> RawEventRecord:
    now = datetime.now(timezone.utc)
    return RawEventRecord(
        id=str(uuid.uuid4()),
        source_type="rss",
        source_name="feed",
        external_id=None,
        url="https://example.com/a",
        title="t",
        raw_text="b",
        published_at=now,
        collected_at=now,
        content_hash="a" * 64,
        theme_hint=None,
        status=status,
        enqueued_msg_id=None,
        error_reason=error_reason,
        event_card_id=None,
        processed_at=None,
        raw_metadata={"requeue_count": requeue_count},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_list_failed_xadd_filters_by_reason_and_limit():
    rows = [
        _rec("xadd_failed: connection refused"),
        _rec("schema error: bad"),  # 제외 (xadd_failed 아님)
        _rec("xadd_failed: timeout", requeue_count=3),  # 제외 (한도 도달)
    ]
    with patch(
        "backend.app.services.reconciler_service.list_by_status_older_than",
        new_callable=AsyncMock,
        return_value=rows,
    ):
        targets = await reconciler_service.list_failed_xadd(AsyncMock(), max_requeue=3)
    assert len(targets) == 1
    assert targets[0].error_reason.startswith("xadd_failed:")


@pytest.mark.asyncio
async def test_requeue_failed_xadd_dry_run_no_requeue():
    rows = [_rec("xadd_failed: x")]
    with patch(
        "backend.app.services.reconciler_service.list_by_status_older_than",
        new_callable=AsyncMock,
        return_value=rows,
    ), patch(
        "backend.app.services.reconciler_service.requeue_raw_event",
        new_callable=AsyncMock,
    ) as mock_requeue:
        targets, n = await reconciler_service.requeue_failed_xadd(AsyncMock(), dry_run=True)
    assert n == 0
    assert len(targets) == 1
    mock_requeue.assert_not_awaited()


@pytest.mark.asyncio
async def test_requeue_failed_xadd_executes_requeue():
    rows = [_rec("xadd_failed: x"), _rec("xadd_failed: y")]
    with patch(
        "backend.app.services.reconciler_service.list_by_status_older_than",
        new_callable=AsyncMock,
        return_value=rows,
    ), patch(
        "backend.app.services.reconciler_service.requeue_raw_event",
        new_callable=AsyncMock,
    ) as mock_requeue:
        targets, n = await reconciler_service.requeue_failed_xadd(AsyncMock(), dry_run=False)
    assert n == 2
    assert mock_requeue.await_count == 2


@pytest.mark.asyncio
async def test_requeue_failed_xadd_continues_on_error():
    rows = [_rec("xadd_failed: x"), _rec("xadd_failed: y")]
    with patch(
        "backend.app.services.reconciler_service.list_by_status_older_than",
        new_callable=AsyncMock,
        return_value=rows,
    ), patch(
        "backend.app.services.reconciler_service.requeue_raw_event",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("redis down"), None],
    ):
        targets, n = await reconciler_service.requeue_failed_xadd(AsyncMock(), dry_run=False)
    # 하나는 실패해도 나머지는 진행 (silent drop 아님, 다음 사이클 재시도)
    assert n == 1
    assert len(targets) == 2
