from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.postgres import get_session
from backend.app.schemas.events import EventSearchResponse, FinalEventCard
from backend.app.services import event_service
from backend.app.services.search_service import OpenSearchUnavailable, search_event_cards

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[FinalEventCard])
async def list_events(session: AsyncSession = Depends(get_session)):
    # 공개 목록은 published 카드만 노출 — hold(미검증/mock 콘텐츠) 카드 차단(05 R-MockCard).
    return await event_service.list_events(session, status="published")


@router.get("/search", response_model=EventSearchResponse)
async def search_events(
    q: str = Query(..., min_length=1, max_length=200),
    theme: str | None = None,
    sector: str | None = None,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> EventSearchResponse:
    try:
        result = await search_event_cards(q, theme, sector, status, limit, offset)
        return EventSearchResponse(**result)
    except OpenSearchUnavailable:
        raise HTTPException(status_code=503, detail="search unavailable")


@router.get("/{event_id}", response_model=FinalEventCard)
async def get_event(event_id: str, session: AsyncSession = Depends(get_session)):
    card = await event_service.get_event(session, event_id)
    # 공개 단건조회도 published 카드만 — hold(미검증/mock 콘텐츠) 카드는 id를 알아도 404
    # (목록 필터를 단건조회로 우회하는 노출경로 차단, 05 R-MockCard).
    if card is None or card.status != "published":
        raise HTTPException(status_code=404, detail="event not found")
    return card
