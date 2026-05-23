from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import redis as redis_db
from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard
from backend.app.schemas.raw_events import RawEventCreate, RawEventCreateResponse
from backend.app.services import event_service
from backend.app.services import raw_event_service

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)

_RAW_STREAM = "stream:raw_events"
_AGENT_STREAM = "stream:to_agent"


@router.get("/jobs")
async def get_jobs() -> dict:
    r = redis_db.get_redis()

    def stream_info(stream: str) -> dict:
        try:
            length = r.xlen(stream)
            groups = r.xinfo_groups(stream)
            return {"length": length, "groups": [g["name"] for g in groups]}
        except Exception:
            return {"length": 0, "groups": []}

    return {
        "raw_events": stream_info(_RAW_STREAM),
        "to_agent": stream_info(_AGENT_STREAM),
    }


@router.post("/upsert-event", response_model=FinalEventCard)
async def upsert_event(card: FinalEventCard, session: AsyncSession = Depends(get_session)):
    return await event_service.upsert_card(session, card)


@router.post("/raw-events", response_model=RawEventCreateResponse)
async def create_raw_event(
    payload: RawEventCreate,
    session: AsyncSession = Depends(get_session),
) -> RawEventCreateResponse:
    # TODO STEP 008: add admin token authentication
    return await raw_event_service.create_raw_event(session, payload)


@router.post("/collect-rss-once")
async def collect_rss_once() -> dict:
    # TODO STEP 008: add admin token authentication
    try:
        from workers.collectors import rss_collector
        summary = await asyncio.to_thread(rss_collector.run)
        return summary
    except Exception as exc:
        logger.error("collect-rss-once failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
