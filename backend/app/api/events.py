from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.postgres import get_session
from backend.app.schemas.events import (
    Event,
    EventSearchResponse,
    EventTimelineResponse,
    FinalEventCard,
)
from backend.app.services import event_service, event_timeline_service
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


# ── Event 타임라인 read API (D-2a, ADR#24) ─────────────────────────────────────────
# `/timeline` 은 `/{event_id}` 보다 **먼저** 선언해야 한다(라우트 우선순위 — 그렇지 않으면
# `/timeline` 이 `/{event_id}` 로 잡혀 event_id="timeline" 으로 처리됨). read-only·결정론(LLM/network 0).
@router.get("/timeline", response_model=list[Event])
async def list_event_timeline(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    # flag off → 미노출(404). 매핑된 실 주제만(held degenerate 제외 — 서비스 계층). event_cards 무관.
    if not settings.EVENT_TIMELINE_API_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    return await event_timeline_service.list_events(session, limit=limit, offset=offset)


@router.get("/timeline/{event_id}", response_model=EventTimelineResponse)
async def get_event_timeline(
    event_id: str, session: AsyncSession = Depends(get_session)
):
    # 단건 Event + append-only EventUpdate 목록. flag off → 404, 미매핑(held degenerate)/없는 event
    # → 404(get_public_event 가 매핑 게이트 강제 — 목록 필터를 단건으로 우회하는 노출 차단, R-MockCard 대칭).
    if not settings.EVENT_TIMELINE_API_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    result = await event_timeline_service.get_public_event(session, event_id)
    if result is None:
        raise HTTPException(status_code=404, detail="event not found")
    event, updates = result
    return EventTimelineResponse(event=event, updates=updates)


@router.get("/{event_id}", response_model=FinalEventCard)
async def get_event(event_id: str, session: AsyncSession = Depends(get_session)):
    card = await event_service.get_event(session, event_id)
    # 공개 단건조회도 published 카드만 — hold(미검증/mock 콘텐츠) 카드는 id를 알아도 404
    # (목록 필터를 단건조회로 우회하는 노출경로 차단, 05 R-MockCard).
    if card is None or card.status != "published":
        raise HTTPException(status_code=404, detail="event not found")
    return card
