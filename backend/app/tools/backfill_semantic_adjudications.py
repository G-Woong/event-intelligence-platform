"""ADR#49 — semantic adjudication backfill tool (read/write adjudication only·incremental·bounded·dry-run).

stage③ ingest 배선(ADR#48)은 배치 흐름 안에서 incremental adjudication 을 돌린다. 이 도구는 그와 별개로 **기존
pending semantic link**(아직 adjudication 이 없는 possible-link)를 bounded chunk(limit)로 backfill 한다 — 운영 DB 에
누적된 미판정 백로그를 주기 job/수동으로 따라잡기 위한 entry. dry-run 지원(영속 전 규모 확인).

불변(상속): **자동 병합 0**(adjudicate_semantic_links = read + adjudication upsert only·events/event_updates/
cluster_event_map 미변경)·idempotent(link_id PK)·결정론(LLM/network 0)·public API 미노출. only_unadjudicated+limit
로 O(N) 전수 재판정 회피(미판정 link 만·bounded). Event count before/after 로 read-only 입증.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.event_resolution import EventIdentityAdjudicationORM, EventLinkORM
from backend.app.models.event_timeline import EventORM
from backend.app.services.semantic_identity_adjudicator import (
    SEMANTIC_LINK_REASON,
    adjudicate_semantic_links,
)


async def _scalar(session: AsyncSession, stmt) -> int:
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_pending_semantic_links(session: AsyncSession) -> int:
    """adjudication 이 아직 없는 possible semantic link 수(pending backlog). NOT IN(adjudication.link_id)."""
    stmt = (
        select(func.count())
        .select_from(EventLinkORM)
        .where(EventLinkORM.status == "possible")
        .where(EventLinkORM.reason == SEMANTIC_LINK_REASON)
        .where(~EventLinkORM.id.in_(select(EventIdentityAdjudicationORM.link_id)))
    )
    return await _scalar(session, stmt)


async def backfill_semantic_adjudications(
    session: AsyncSession, *, limit: Optional[int] = None, dry_run: bool = False,
) -> dict:
    """기존 pending semantic link → incremental shadow adjudication backfill(bounded·dry-run). 자동 병합 0.

    dry_run=True 면 영속하지 않고 규모만 산출(pending_before·예상 processed). limit 이면 1회 chunk 상한(결정론).
    Event count before/after 로 read-only(자동 병합 0) 입증."""
    before_e = await _scalar(session, select(func.count()).select_from(EventORM))
    pending_before = await count_pending_semantic_links(session)
    results = await adjudicate_semantic_links(
        session, persist=not dry_run, only_unadjudicated=True, limit=limit)
    pending_after = await count_pending_semantic_links(session)
    after_e = await _scalar(session, select(func.count()).select_from(EventORM))
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {
        "dry_run": dry_run,
        "limit": limit,
        "pending_before": pending_before,
        "processed": len(results),                  # dry_run 면 영속 0(would-process 규모만)
        "pending_after": pending_after,             # dry_run 면 == pending_before(영속 0)
        "by_status": by_status,
        "event_count_before": before_e,
        "event_count_after": after_e,               # == before(read + adjudication write only)
        "auto_merge_enabled": False,
    }
