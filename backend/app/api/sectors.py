from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard
from backend.app.services import event_service

router = APIRouter(prefix="/api/sectors", tags=["sectors"])

_SECTORS = [
    {"id": "energy", "name": "Energy", "label": "Energy",
     "description": "에너지/석유/가스/전력 관련 이벤트"},
    {"id": "finance", "name": "Finance", "label": "Finance",
     "description": "금융/은행/자본시장 관련 이벤트"},
    {"id": "defense", "name": "Defense", "label": "Defense",
     "description": "국방/방산/군사 관련 이벤트"},
    {"id": "tech", "name": "Technology", "label": "Technology",
     "description": "기술/반도체/소프트웨어 관련 이벤트"},
    {"id": "trade", "name": "Trade", "label": "Trade",
     "description": "무역/관세/공급망 관련 이벤트"},
]


@router.get("")
async def list_sectors(session: AsyncSession = Depends(get_session)):
    try:
        counts = await event_service.count_by_sector(session)
    except Exception:
        counts = {}
    return [{**t, "event_count": counts.get(t["id"], 0)} for t in _SECTORS]


@router.get("/{sector_id}/events", response_model=list[FinalEventCard])
async def events_by_sector(sector_id: str, session: AsyncSession = Depends(get_session)):
    return await event_service.list_by_sector(session, sector_id)
