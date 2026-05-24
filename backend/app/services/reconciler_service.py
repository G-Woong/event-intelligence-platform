from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.raw_event import RawEventORM
from backend.app.schemas.raw_events import RawEventRecord
from .raw_event_service import list_by_status_older_than


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
