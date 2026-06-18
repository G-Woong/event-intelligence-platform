from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.raw_event import RawEventORM
from backend.app.schemas.raw_events import RawEventRecord
from .raw_event_service import list_by_status_older_than, requeue_raw_event

logger = logging.getLogger(__name__)

_XADD_FAILED_PREFIX = "xadd_failed:"


async def list_stuck_enqueued(
    session: AsyncSession,
    before_seconds: int = 600,
    limit: int = 100,
) -> list[RawEventRecord]:
    return await list_by_status_older_than(
        session, status="enqueued", before_seconds=before_seconds, limit=limit
    )


async def mark_stuck_as_failed(
    session: AsyncSession,
    before_seconds: int = 600,
    limit: int = 100,
    error_reason: str = "reconciler: stuck enqueued",
    dry_run: bool = True,
) -> tuple[list[RawEventRecord], int]:
    items = await list_stuck_enqueued(session, before_seconds=before_seconds, limit=limit)
    if dry_run or not items:
        return items, 0
    ids = [item.id for item in items]
    await session.execute(
        update(RawEventORM)
        .where(RawEventORM.id.in_(ids))
        .values(
            status="failed",
            error_reason=error_reason[:500],
            processed_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()
    return items, len(ids)


async def list_failed_xadd(
    session: AsyncSession,
    limit: int = 100,
    max_requeue: int = 3,
) -> list[RawEventRecord]:
    """status=failed 이면서 사유가 xadd_failed 이고 requeue 한도 미만인 행.

    create_raw_event는 PG commit 후 Redis XADD를 시도하므로(PG-first), XADD 실패 시 행은
    status=failed/error_reason=xadd_failed:* 로 남는다(orphan Redis 메시지 없음). 이를 자동 회수한다.
    """
    candidates = await list_by_status_older_than(session, status="failed", limit=limit)
    targets: list[RawEventRecord] = []
    for record in candidates:
        if not (record.error_reason or "").startswith(_XADD_FAILED_PREFIX):
            continue
        requeue_count = int((record.raw_metadata or {}).get("requeue_count", 0))
        if requeue_count >= max_requeue:
            # poison 방지: 한도 초과는 자동 requeue 대상에서 제외(수동 개입/DLQ 검토).
            continue
        targets.append(record)
    return targets


async def requeue_failed_xadd(
    session: AsyncSession,
    limit: int = 100,
    max_requeue: int = 3,
    dry_run: bool = True,
) -> tuple[list[RawEventRecord], int]:
    """xadd_failed 행을 Redis로 자동 재발행한다. 반환: (대상목록, 실제 requeue 수)."""
    targets = await list_failed_xadd(session, limit=limit, max_requeue=max_requeue)
    if dry_run or not targets:
        return targets, 0
    requeued = 0
    for record in targets:
        try:
            await requeue_raw_event(session, record.id, force=False)
            requeued += 1
        except Exception as exc:  # redis 여전히 불가 등 — 다음 사이클로 미룸
            logger.warning("requeue_failed_xadd: requeue failed id=%s reason=%s", record.id, str(exc)[:200])
    return targets, requeued
