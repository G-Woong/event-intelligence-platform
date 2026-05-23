from __future__ import annotations

from fastapi import APIRouter
from backend.app.schemas.events import FinalEventCard
from backend.app.services import event_service

router = APIRouter(prefix="/api/themes", tags=["themes"])

_THEMES = [
    {"id": "geopolitics", "label": "Geopolitics"},
    {"id": "economics", "label": "Economics"},
    {"id": "technology", "label": "Technology"},
    {"id": "climate", "label": "Climate"},
    {"id": "health", "label": "Health"},
]


@router.get("")
def list_themes():
    return _THEMES


@router.get("/{theme_id}/events", response_model=list[FinalEventCard])
def events_by_theme(theme_id: str):
    return [e for e in event_service.list_events() if e.theme == theme_id]
