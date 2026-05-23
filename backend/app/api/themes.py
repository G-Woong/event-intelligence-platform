from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.postgres import get_session
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
async def list_themes():
    return _THEMES


@router.get("/{theme_id}/events", response_model=list[FinalEventCard])
async def events_by_theme(theme_id: str, session: AsyncSession = Depends(get_session)):
    return await event_service.list_by_theme(session, theme_id)
