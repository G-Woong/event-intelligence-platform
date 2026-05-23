from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard
from backend.app.services import event_service

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[FinalEventCard])
async def list_events(session: AsyncSession = Depends(get_session)):
    return await event_service.list_events(session)


@router.get("/{event_id}", response_model=FinalEventCard)
async def get_event(event_id: str, session: AsyncSession = Depends(get_session)):
    card = await event_service.get_event(session, event_id)
    if card is None:
        raise HTTPException(status_code=404, detail="event not found")
    return card
