from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import redis as redis_db
from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard
from backend.app.schemas.raw_events import (
    RawEventCreate,
    RawEventCreateResponse,
    RawEventRecord,
    RawEventStatusUpdate,
    ReconcileStuckRequest,
    ReconcileStuckResponse,
)
from backend.app.services import event_service
from backend.app.services import raw_event_service
from backend.app.services import reconciler_service

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)

_RAW_STREAM = "stream:raw_events"
_AGENT_STREAM = "stream:to_agent"


@router.get("/jobs")
async def get_jobs() -> dict:
    r = redis_db.get_redis()

    def stream_info(stream: str) -> dict:
        try:
            length = r.xlen(stream)
            groups = r.xinfo_groups(stream)
            return {"length": length, "groups": [g["name"] for g in groups]}
        except Exception:
            return {"length": 0, "groups": []}

    return {
        "raw_events": stream_info(_RAW_STREAM),
        "to_agent": stream_info(_AGENT_STREAM),
    }


@router.post("/upsert-event", response_model=FinalEventCard)
async def upsert_event(card: FinalEventCard, session: AsyncSession = Depends(get_session)):
    return await event_service.upsert_card(session, card)


@router.post("/raw-events/reconcile-stuck", response_model=ReconcileStuckResponse)
async def reconcile_stuck(
    body: ReconcileStuckRequest,
    session: AsyncSession = Depends(get_session),
) -> ReconcileStuckResponse:
    items, marked = await reconciler_service.mark_stuck_as_failed(
        session,
        before_seconds=body.before_seconds,
        limit=body.limit,
        error_reason=body.error_reason,
        dry_run=body.dry_run,
    )
    return ReconcileStuckResponse(
        stuck_count=len(items),
        marked_failed=marked,
        dry_run=body.dry_run,
        items=items,
    )


@router.post("/raw-events", response_model=RawEventCreateResponse)
async def create_raw_event(
    payload: RawEventCreate,
    session: AsyncSession = Depends(get_session),
) -> RawEventCreateResponse:
    # TODO STEP 008C: add admin token authentication
    return await raw_event_service.create_raw_event(session, payload)


@router.get("/raw-events", response_model=list[RawEventRecord])
async def list_raw_events(
    status: str | None = None,
    before_seconds: int | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[RawEventRecord]:
    return await raw_event_service.list_by_status_older_than(
        session, status=status, before_seconds=before_seconds, limit=limit
    )


@router.get("/raw-events/{raw_event_id}", response_model=RawEventRecord)
async def get_raw_event(
    raw_event_id: str,
    session: AsyncSession = Depends(get_session),
) -> RawEventRecord:
    try:
        return await raw_event_service.get_raw_event(session, raw_event_id)
    except NoResultFound:
        raise HTTPException(status_code=404, detail=f"raw_event_id={raw_event_id} not found")


@router.patch("/raw-events/{raw_event_id}/status", response_model=RawEventRecord)
async def update_raw_event_status(
    raw_event_id: str,
    body: RawEventStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> RawEventRecord:
    try:
        return await raw_event_service.update_status(
            session,
            raw_event_id,
            status=body.status,
            error_reason=body.error_reason,
            event_card_id=body.event_card_id,
        )
    except NoResultFound:
        raise HTTPException(status_code=404, detail=f"raw_event_id={raw_event_id} not found")


@router.post("/collect-rss-once")
async def collect_rss_once() -> dict:
    # TODO STEP 008C: add admin token authentication
    try:
        from workers.collectors import rss_collector
        summary = await asyncio.to_thread(rss_collector.run)
        return summary
    except Exception as exc:
        logger.error("collect-rss-once failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
