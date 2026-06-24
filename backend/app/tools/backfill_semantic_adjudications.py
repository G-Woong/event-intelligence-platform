"""ADR#49/#50 — semantic adjudication backfill tool (read/write adjudication only·incremental·keyset·dry-run·CLI).

stage③ ingest 배선(ADR#48)은 배치 흐름 안에서 incremental adjudication 을 돌린다. 이 도구는 그와 별개로 **기존
pending semantic link**(아직 adjudication 이 없는 possible-link)를 bounded chunk(limit)로 backfill 한다 — 운영 DB 에
누적된 미판정 백로그를 주기 job/수동으로 따라잡기 위한 entry. dry-run 지원(영속 전 규모 확인).

**운영 실행(ADR#50):** `python -m backend.app.tools.backfill_semantic_adjudications [--limit N] [--after-link-id ID]
[--dry-run] [--allow-non-dev-db]`. DB write 대상 가드(assert_safe_write_target — dev/test 만, staging/production 은
명시 opt-in)를 seed 도구와 공유(fail-closed). 주기 가동은 새 scheduler 가 아니라 **기존 run_recovery_scheduler 식
`--once` cron/docker 관용구 재사용**(운영 DB 0003→0009 migration 이후 — 미마이그레이션 DB 에선 테이블 부재로 게이트).

불변(상속): **자동 병합 0**(adjudicate_semantic_links = read + adjudication upsert only·events/event_updates/
cluster_event_map 미변경)·결정론(LLM/network 0)·public API 미노출. only_unadjudicated+limit+after_link_id 로
O(전체) scan 완화(미판정 link 만·keyset bounded). Event count before/after 로 read-only 입증.

**동시성 정직 경계:** link_id PK `on_conflict_do_update` upsert → **중복행 0**(데이터 안전). 단 이는 **lock 이 아니라**
deterministic classifier(같은 link→같은 status) + last-writer-wins 라서 무해한 것 — 동시 실행 시 같은 미판정 link 를
양쪽이 중복 view-load/판정할 수 있다(중복 work·절감 무효). 양쪽 모두 `ORDER BY id asc` 동일 잠금 순서라 ABBA deadlock
회피(설계). **OS-병렬 race/deadlock 은 stress-test 안 됨** — 중복 work 회피가 필요하면 단일 runner 또는 disjoint
`--after-link-id` 범위로 운영(직렬화/advisory lock 미구현). report 는 `idempotent_persist=True`(중복행 0)만 주장하고
lock 안전을 **과대주장하지 않는다**. **keyset cursor 는 UUIDv4 byte 순서(시간순 아님)** — 진행 보장은 only_unadjudicated.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.config import settings
from backend.app.models.event_resolution import EventIdentityAdjudicationORM, EventLinkORM
from backend.app.models.event_timeline import EventORM
from backend.app.services.semantic_identity_adjudicator import (
    SEMANTIC_LINK_REASON,
    adjudicate_semantic_links,
)
from backend.app.tools.db_target import assert_safe_write_target


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
    session: AsyncSession, *, limit: Optional[int] = None,
    after_link_id: Optional[str] = None, dry_run: bool = False,
) -> dict:
    """기존 pending semantic link → incremental shadow adjudication backfill(keyset bounded·dry-run). 자동 병합 0.

    dry_run=True 면 영속하지 않고 규모만 산출(pending_before·예상 processed). limit 이면 1회 chunk 상한(결정론).
    after_link_id 면 그 link_id **초과**만(keyset cursor·UUIDv4 byte 순서·시간순 아님·재현 가능 페이지 경계). Event
    count before/after 로 read-only 입증.

    report 의 next_cursor = 마지막 처리된 link_id(다음 run `--after-link-id` 로 페이지 진행); **진행/완전성 보장은 cursor
    가 아니라 only_unadjudicated**(판정된 link 가 빠짐). Event 소실 link 만 tail 에 남으면 only_unadjudicated 로 안 빠지므로
    (영속 안 됨) 별도 정리 필요(정직). full_scan=True = limit/cursor 미지정(전체 scan 경고·대형 백로그 시 cursor 페이지 권고)."""
    before_e = await _scalar(session, select(func.count()).select_from(EventORM))
    pending_before = await count_pending_semantic_links(session)
    results = await adjudicate_semantic_links(
        session, persist=not dry_run, only_unadjudicated=True,
        limit=limit, after_link_id=after_link_id)
    pending_after = await count_pending_semantic_links(session)
    after_e = await _scalar(session, select(func.count()).select_from(EventORM))
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {
        "dry_run": dry_run,
        "limit": limit,
        "after_link_id": after_link_id,
        "pending_before": pending_before,
        "processed": len(results),                  # dry_run 면 영속 0(would-process 규모만)
        "pending_after": pending_after,             # dry_run 면 == pending_before(영속 0)
        "by_status": by_status,
        "event_count_before": before_e,
        "event_count_after": after_e,               # == before(read + adjudication write only)
        "next_cursor": results[-1].link_id if results else after_link_id,  # 다음 페이지 경계(UUIDv4·시간순 아님)
        "full_scan": limit is None and after_link_id is None,   # bounded 아님(전체 scan) 경고
        "idempotent_persist": True,                 # link_id PK upsert → 중복행 0(데이터 안전·lock 아님·work 중복 가능)
        "auto_merge_enabled": False,
    }


# ── 운영 CLI(ADR#50; seed_event_timeline 관용구 — argparse + safe-target + asyncio.run) ──────
async def _run(*, limit: Optional[int], after_link_id: Optional[str], dry_run: bool) -> dict:
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            return await backfill_semantic_adjudications(
                session, limit=limit, after_link_id=after_link_id, dry_run=dry_run)
    finally:
        await engine.dispose()


def main(argv: Optional[list[str]] = None) -> int:
    try:  # Windows cp949 콘솔이 한국어/em-dash help·report 에 죽지 않도록 utf-8(closeout_sig 선례).
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="semantic adjudication backfill (pending possible-link → shadow adjudication·자동 병합 0).",
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="1회 chunk 상한(bounded backfill). 미지정=전체(full_scan 경고).")
    parser.add_argument("--after-link-id", default=None,
                        help="keyset cursor — 이 link_id 초과 link 만(페이지네이션 진행).")
    parser.add_argument("--dry-run", action="store_true",
                        help="영속 없이 규모만 산출(pending_before·would-process). 운영 적용 전 확인.")
    parser.add_argument("--allow-non-dev-db", action="store_true",
                        help="APP_ENV=staging/production DB 에도 허용(기본 거부 — fail-closed).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # R-EventSinkDbTarget 가드(seed 와 동일 정책): 비-dev DB 는 명시 허용 없이 거부 + 대상 출력(자격증명 제외).
    label = assert_safe_write_target(
        app_env=settings.APP_ENV, database_url=settings.DATABASE_URL,
        allow_non_dev=ns.allow_non_dev_db)
    print(f"- backfill target DB: {label} (APP_ENV={settings.APP_ENV})")

    report = asyncio.run(_run(limit=ns.limit, after_link_id=ns.after_link_id, dry_run=ns.dry_run))
    print(
        f"- backfill: dry_run={report['dry_run']} limit={report['limit']} "
        f"after_link_id={report['after_link_id']} processed={report['processed']} "
        f"pending {report['pending_before']}->{report['pending_after']} by_status={report['by_status']} "
        f"next_cursor={report['next_cursor']} full_scan={report['full_scan']} "
        f"event_count {report['event_count_before']}->{report['event_count_after']} "
        f"auto_merge={report['auto_merge_enabled']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
