from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard
from backend.app.services import event_service

router = APIRouter(prefix="/api/themes", tags=["themes"])

_THEMES = [
    {"id": "geopolitics", "name": "Geopolitics", "label": "Geopolitics",
     "description": "국가/외교/안보 관련 이벤트"},
    {"id": "economics", "name": "Economics", "label": "Economics",
     "description": "경제/금융/무역 관련 이벤트"},
    {"id": "technology", "name": "Technology", "label": "Technology",
     "description": "기술/사이버/혁신 관련 이벤트"},
    {"id": "climate", "name": "Climate", "label": "Climate",
     "description": "기후/환경/자연재해 관련 이벤트"},
    {"id": "health", "name": "Health", "label": "Health",
     "description": "보건/의료/전염병 관련 이벤트"},
]


@router.get("")
async def list_themes(session: AsyncSession = Depends(get_session)):
    try:
        counts = await event_service.count_by_theme(session)
    except Exception:
        counts = {}
    return [{**t, "event_count": counts.get(t["id"], 0)} for t in _THEMES]


@router.get("/{theme_id}/events", response_model=list[FinalEventCard])
async def events_by_theme(theme_id: str, session: AsyncSession = Depends(get_session)):
    return await event_service.list_by_theme(session, theme_id)
