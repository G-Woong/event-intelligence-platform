from __future__ import annotations

from fastapi import APIRouter, HTTPException
from backend.app.schemas.events import FinalEventCard
from backend.app.services import event_service

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[FinalEventCard])
def list_events():
    return event_service.list_events()


@router.get("/{event_id}", response_model=FinalEventCard)
def get_event(event_id: str):
    card = event_service.get_event(event_id)
    if card is None:
        raise HTTPException(status_code=404, detail="event not found")
    return card
