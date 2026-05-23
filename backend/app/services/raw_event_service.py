from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.raw_event import RawEventORM
from backend.app.schemas.events import RawEvent
from backend.app.schemas.raw_events import RawEventCreate, RawEventCreateResponse, RawEventRecord
from workers.queue.producer import enqueue_raw_event

logger = logging.getLogger(__name__)

_MAX_URL_LEN = 2048


def _orm_to_record(row: RawEventORM) -> RawEventRecord:
    return RawEventRecord(
        id=str(row.id),
        source_type=row.source_type,
        source_name=row.source_name,
        external_id=row.external_id,
        url=row.url,
        title=row.title,
        raw_text=row.raw_text,
        published_at=row.published_at,
        collected_at=row.collected_at,
        content_hash=row.content_hash,
        theme_hint=row.theme_hint,
        status=row.status,
        enqueued_msg_id=row.enqueued_msg_id,
        error_reason=row.error_reason,
        raw_metadata=row.raw_metadata or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_raw_event(session: AsyncSession, payload: RawEventCreate) -> RawEventCreateResponse:
    url = payload.url[:_MAX_URL_LEN]
    if len(payload.url) > _MAX_URL_LEN:
        logger.warning("url truncated from %d chars for hash=%s", len(payload.url), payload.content_hash)

    row_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    stmt = (
        pg_insert(RawEventORM)
        .values(
            id=row_id,
            source_type=payload.source_type,
            source_name=payload.source_name,
            external_id=payload.external_id,
            url=url,
            title=payload.title,
            raw_text=payload.raw_text,
            published_at=payload.published_at,
            collected_at=now,
            content_hash=payload.content_hash,
            theme_hint=payload.theme_hint,
            status="collected",
            raw_metadata=payload.raw_metadata,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["content_hash"])
    )
    await session.execute(stmt)
    await session.commit()

    result = await session.execute(
        select(RawEventORM).where(RawEventORM.content_hash == payload.content_hash)
    )
    row = result.scalar_one()
    is_duplicate = str(row.id) != str(row_id)

    if is_duplicate:
        return RawEventCreateResponse(
            record=_orm_to_record(row),
            is_duplicate=True,
            enqueued_msg_id=None,
        )

    enqueued_msg_id: str | None = None
    try:
        raw_event = RawEvent(
            source=f"rss:{payload.source_name}",
            url=url,
            fetched_at=now,
            raw_text=payload.raw_text,
            raw_metadata=payload.raw_metadata,
        )
        enqueued_msg_id = await asyncio.to_thread(enqueue_raw_event, raw_event)
        await session.execute(
            update(RawEventORM)
            .where(RawEventORM.id == row.id)
            .values(status="enqueued", enqueued_msg_id=enqueued_msg_id, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
        row.status = "enqueued"
        row.enqueued_msg_id = enqueued_msg_id
    except Exception as exc:
        logger.error("XADD failed for content_hash=%s: %s", payload.content_hash, exc)

    return RawEventCreateResponse(
        record=_orm_to_record(row),
        is_duplicate=False,
        enqueued_msg_id=enqueued_msg_id,
    )
