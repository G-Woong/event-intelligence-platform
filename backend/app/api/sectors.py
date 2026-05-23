from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard
from backend.app.services import event_service

router = APIRouter(prefix="/api/sectors", tags=["sectors"])

_SECTORS = [
    {"id": "energy", "label": "Energy"},
    {"id": "finance", "label": "Finance"},
    {"id": "defense", "label": "Defense"},
    {"id": "tech", "label": "Technology"},
    {"id": "trade", "label": "Trade"},
]


@router.get("")
async def list_sectors():
    return _SECTORS


@router.get("/{sector_id}/events", response_model=list[FinalEventCard])
async def events_by_sector(sector_id: str, session: AsyncSession = Depends(get_session)):
    return await event_service.list_by_sector(session, sector_id)
