from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, type_coerce
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.event import EventCardORM
from backend.app.schemas.events import FinalEventCard

logger = logging.getLogger(__name__)


def _card_to_orm_values(card: FinalEventCard) -> dict[str, Any]:
    try:
        card_id = uuid.UUID(card.id)
    except (ValueError, AttributeError):
        logger.warning("invalid card.id %r — assigning new UUID", card.id)
        card_id = uuid.uuid4()
    created_at = card.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "id": card_id,
        "title": card.title,
        "summary": card.summary,
        "theme": card.theme,
        "impact_path": card.impact_path,
        "status": card.status,
        "sectors": card.sectors,
        "entities": card.entities,
        "evidence": card.evidence,
        "confidence_score": card.confidence_score,
        "created_at": created_at,
    }


def _orm_to_card(row: EventCardORM) -> FinalEventCard:
    return FinalEventCard(
        id=str(row.id),
        title=row.title,
        summary=row.summary,
        theme=row.theme,
        sectors=row.sectors or [],
        entities=row.entities or [],
        impact_path=row.impact_path or "",
        evidence=row.evidence or [],
        confidence_score=row.confidence_score,
        status=row.status,
        created_at=row.created_at,
    )


async def list_events(session: AsyncSession) -> list[FinalEventCard]:
    stmt = select(EventCardORM).order_by(EventCardORM.created_at.desc())
    result = await session.execute(stmt)
    return [_orm_to_card(row) for row in result.scalars()]


async def get_event(session: AsyncSession, event_id: str) -> FinalEventCard | None:
    try:
        eid = uuid.UUID(event_id)
    except (ValueError, AttributeError):
        return None
    stmt = select(EventCardORM).where(EventCardORM.id == eid)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return _orm_to_card(row) if row is not None else None


async def upsert_card(session: AsyncSession, card: FinalEventCard) -> FinalEventCard:
    values = _card_to_orm_values(card)
    stmt = pg_insert(EventCardORM.__table__).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "title": stmt.excluded.title,
            "summary": stmt.excluded.summary,
            "theme": stmt.excluded.theme,
            "impact_path": stmt.excluded.impact_path,
            "status": stmt.excluded.status,
            "sectors": stmt.excluded.sectors,
            "entities": stmt.excluded.entities,
            "evidence": stmt.excluded.evidence,
            "confidence_score": stmt.excluded.confidence_score,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    await session.commit()
    return card


async def list_by_theme(session: AsyncSession, theme: str) -> list[FinalEventCard]:
    stmt = (
        select(EventCardORM)
        .where(EventCardORM.theme == theme)
        .order_by(EventCardORM.created_at.desc())
    )
    result = await session.execute(stmt)
    return [_orm_to_card(row) for row in result.scalars()]


async def list_by_sector(session: AsyncSession, sector: str) -> list[FinalEventCard]:
    stmt = (
        select(EventCardORM)
        .where(EventCardORM.sectors.op("@>")(type_coerce([sector], JSONB)))
        .order_by(EventCardORM.created_at.desc())
    )
    result = await session.execute(stmt)
    return [_orm_to_card(row) for row in result.scalars()]
