from __future__ import annotations

from fastapi import APIRouter
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
def list_sectors():
    return _SECTORS


@router.get("/{sector_id}/events", response_model=list[FinalEventCard])
def events_by_sector(sector_id: str):
    return [e for e in event_service.list_events() if sector_id in e.sectors]
