from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import redis as redis_db
from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard
from backend.app.services import event_service

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
