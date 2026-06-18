from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import redis as redis_db
from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard, ReindexRequest, ReindexResponse
from backend.app.schemas.raw_events import (
    RawEventCreate,
    RawEventCreateResponse,
    RawEventRecord,
    RawEventStatusUpdate,
    ReconcileStuckRequest,
    ReconcileStuckResponse,
    RequeueFailedXaddRequest,
    RequeueFailedXaddResponse,
    RequeueRequest,
    RequeueResponse,
)
from backend.app.services import event_service
from backend.app.services import opensearch_index_service
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


@router.post("/raw-events/requeue-failed-xadd", response_model=RequeueFailedXaddResponse)
async def requeue_failed_xadd(
    body: RequeueFailedXaddRequest,
    session: AsyncSession = Depends(get_session),
) -> RequeueFailedXaddResponse:
    """xadd_failed 행(PG는 됐으나 Redis XADD 실패)을 자동 재발행한다. poison은 max_requeue로 차단."""
    items, requeued = await reconciler_service.requeue_failed_xadd(
        session,
        limit=body.limit,
        max_requeue=body.max_requeue,
        dry_run=body.dry_run,
    )
    return RequeueFailedXaddResponse(
        candidate_count=len(items),
        requeued=requeued,
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
    source_type: str | None = None,
    offset: int = 0,
    order: str = "asc",
    session: AsyncSession = Depends(get_session),
) -> list[RawEventRecord]:
    return await raw_event_service.list_by_status_older_than(
        session,
        status=status,
        before_seconds=before_seconds,
        limit=limit,
        source_type=source_type,
        offset=offset,
        order=order,
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


@router.post("/raw-events/{raw_event_id}/requeue", response_model=RequeueResponse)
async def requeue_raw_event(
    raw_event_id: str,
    body: RequeueRequest,
    session: AsyncSession = Depends(get_session),
) -> RequeueResponse:
    try:
        record, msg_id, requeue_count = await raw_event_service.requeue_raw_event(
            session, raw_event_id, force=body.force
        )
        return RequeueResponse(record=record, enqueued_msg_id=msg_id, requeue_count=requeue_count)
    except NoResultFound:
        raise HTTPException(status_code=404, detail=f"raw_event_id={raw_event_id} not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


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


@router.post("/search/reindex", response_model=ReindexResponse)
async def reindex_search(
    body: ReindexRequest,
    session: AsyncSession = Depends(get_session),
) -> ReindexResponse:
    cards = await event_service.list_events(session, limit=body.limit)
    if not body.dry_run:
        opensearch_index_service.ensure_event_cards_index()
        for card in cards:
            opensearch_index_service.try_index_card(card)
    return ReindexResponse(indexed=len(cards), dry_run=body.dry_run)


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
