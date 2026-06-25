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
from datetime import datetime
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
from backend.app.tools.db_target import UnsafeWriteTargetError, assert_safe_write_target
from backend.app.tools.identity_backlog_readiness import operational_db_readiness


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
    after_link_id: Optional[str] = None, after_created_at: Optional[datetime] = None,
    cursor_mode: str = "id", dry_run: bool = False,
) -> dict:
    """기존 pending semantic link → incremental shadow adjudication backfill(keyset bounded·dry-run). 자동 병합 0.

    dry_run=True 면 영속하지 않고 규모만 산출(pending_before·예상 processed). limit 이면 1회 chunk 상한(결정론).
    cursor_mode='id'(default)면 after_link_id **초과**(keyset cursor·UUIDv4 byte 순서·시간순 아님); 'created_at'이면
    (after_created_at, after_link_id) **초과**(시간순 복합 cursor·배치 간 정확·intra-batch tie→id — `_semantic_links`
    정직 경계 참조). Event count before/after 로 read-only 입증.

    report 의 next_cursor/next_created_at = 마지막 처리된 link 의 (id, created_at)(다음 run cursor 로 페이지 진행);
    **진행/완전성 보장은 cursor 가 아니라 only_unadjudicated**(판정된 link 가 빠짐). Event 소실 link 만 tail 에 남으면
    only_unadjudicated 로 안 빠지므로(영속 안 됨) 별도 정리 필요(정직). full_scan=True = limit/cursor 미지정(전체 scan 경고·
    대형 백로그 시 cursor 페이지 권고; scheduler 는 항상 --limit 으로 full_scan 회피)."""
    before_e = await _scalar(session, select(func.count()).select_from(EventORM))
    pending_before = await count_pending_semantic_links(session)
    results = await adjudicate_semantic_links(
        session, persist=not dry_run, only_unadjudicated=True,
        limit=limit, after_link_id=after_link_id, after_created_at=after_created_at,
        cursor_mode=cursor_mode)
    pending_after = await count_pending_semantic_links(session)
    after_e = await _scalar(session, select(func.count()).select_from(EventORM))
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    last = results[-1] if results else None
    return {
        "dry_run": dry_run,
        "limit": limit,
        "cursor_mode": cursor_mode,
        "after_link_id": after_link_id,
        "after_created_at": after_created_at.isoformat() if after_created_at else None,
        "pending_before": pending_before,
        "processed": len(results),                  # dry_run 면 영속 0(would-process 규모만)
        "pending_after": pending_after,             # dry_run 면 == pending_before(영속 0)
        "by_status": by_status,
        "event_count_before": before_e,
        "event_count_after": after_e,               # == before(read + adjudication write only)
        # 다음 페이지 경계 — id 모드=link_id(UUIDv4·시간순 아님)·created_at 모드=(next_created_at, next_cursor) 복합.
        "next_cursor": last.link_id if last else after_link_id,
        "next_created_at": (last.link_created_at.isoformat()
                            if (last is not None and last.link_created_at is not None)
                            else (after_created_at.isoformat() if after_created_at else None)),
        "full_scan": limit is None and after_link_id is None and after_created_at is None,   # 전체 scan 경고
        "idempotent_persist": True,                 # link_id PK upsert → 중복행 0(데이터 안전·lock 아님·work 중복 가능)
        "auto_merge_enabled": False,
    }


async def backfill_preflight(session: AsyncSession, *, allow_flag_off: bool = False) -> dict:
    """운영 backfill persist 전 게이트(readiness + flag) — read-only.

    **ready_for_stage3 hard gate:** False(adjudication 테이블 부재 — 운영 DB 0003 등)면 backfill 쿼리(NOT IN adjudication)가
    크래시하므로 **dry-run 포함 전부 차단**해야 한다(Q16). **flag gate:** EVENT_SEMANTIC_ADJUDICATION_ENABLED off 면 persist
    만 차단(dry-run 은 read-only 라 허용). allow_flag_off=True 는 flag gate 명시 우회(운영자/테스트 opt-in). safe-target(write
    DB) 가드는 이 함수 밖(assert_safe_write_target — 세션 열기 전·fail-closed)."""
    readiness = await operational_db_readiness(session)
    ready = bool(readiness.get("ready_for_stage3"))
    flag_enabled = bool(settings.EVENT_SEMANTIC_ADJUDICATION_ENABLED)
    return {
        "ready_for_stage3": ready,
        "current_revision": readiness.get("current_revision"),
        "behind_count": readiness.get("behind_count"),
        "flag_enabled": flag_enabled,
        "allow_flag_off": allow_flag_off,
        # persist 가능 여부: 테이블 준비 + (flag on 또는 명시 우회). dry-run 은 ready 만 충족하면 가능.
        "persist_allowed": ready and (flag_enabled or allow_flag_off),
    }


def decide_exit_code(out: dict) -> int:
    """preflight/backfill 결과 dict → deterministic exit code(scheduler/cron 관측용·ADR#51).

    0=성공(persist 또는 미판정 0) · 1=blocked(readiness/flag preflight 미충족) · 3=dry-run 인데 pending 남음(백로그 미배수).
    2(runtime error)·1(unsafe target)는 main() 가 직접 반환(이 함수는 ran/blocked·dry-run 만 판정)."""
    if not out.get("ran"):
        return 1                                    # readiness/flag preflight 차단 → persist 안 함
    report = out["report"]
    if report["dry_run"] and report["pending_after"] > 0:
        return 3                                    # dry-run 으로 백로그 미배수(정보용 nonzero)
    return 0


async def run_backfill_with_preflight(
    session: AsyncSession, *, limit: Optional[int] = None,
    after_link_id: Optional[str] = None, after_created_at: Optional[datetime] = None,
    cursor_mode: str = "id", dry_run: bool = False, allow_flag_off: bool = False,
) -> dict:
    """preflight(readiness/flag) 게이트 후 backfill — **CLI/scheduler 공유 진입점**. {preflight, report, ran, block} 반환.

    ready_for_stage3=False → dry-run 포함 미실행(쿼리 크래시 방지·Q16). persist 요청 + flag off + 우회 없음 → persist 미실행
    (block='flag'). 그 외 backfill 실행(dry_run 그대로). safe-target 가드는 호출자(세션 열기 전·fail-closed)."""
    pre = await backfill_preflight(session, allow_flag_off=allow_flag_off)
    if not pre["ready_for_stage3"]:
        return {"preflight": pre, "report": None, "ran": False, "block": "readiness"}
    if not dry_run and not pre["persist_allowed"]:
        return {"preflight": pre, "report": None, "ran": False, "block": "flag"}
    report = await backfill_semantic_adjudications(
        session, limit=limit, after_link_id=after_link_id, after_created_at=after_created_at,
        cursor_mode=cursor_mode, dry_run=dry_run)
    return {"preflight": pre, "report": report, "ran": True, "block": None}


# ── 운영 진입점(CLI/scheduler 공유) + CLI(ADR#50/#51; seed 관용구 — argparse + safe-target + preflight + exit code) ──
async def run_backfill_session(
    *, limit: Optional[int] = None, after_link_id: Optional[str] = None,
    after_created_at: Optional[datetime] = None, cursor_mode: str = "id",
    dry_run: bool = False, allow_flag_off: bool = False,
) -> dict:
    """settings.DATABASE_URL 엔진/세션 열고 run_backfill_with_preflight 호출 — **CLI/scheduler 공유 진입점**.
    {preflight, report, ran, block} 반환(→ decide_exit_code 입력)."""
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            return await run_backfill_with_preflight(
                session, limit=limit, after_link_id=after_link_id, after_created_at=after_created_at,
                cursor_mode=cursor_mode, dry_run=dry_run, allow_flag_off=allow_flag_off)
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
    parser.add_argument("--after-created-at", default=None,
                        help="created_at cursor(ISO8601) — --cursor-mode created_at 와 함께 시간순 페이지 진행.")
    parser.add_argument("--cursor-mode", choices=("id", "created_at"), default="id",
                        help="id=UUIDv4 byte 순서(default·하위호환)·created_at=시간순 복합 cursor(오래된 백로그 우선·"
                             "배치 간 정확·동일 배치 내 임의·인덱스 없음).")
    parser.add_argument("--dry-run", action="store_true",
                        help="영속 없이 규모만 산출(pending_before·would-process). 운영 적용 전 확인.")
    parser.add_argument("--allow-non-dev-db", action="store_true",
                        help="APP_ENV=staging/production DB 에도 허용(기본 거부 — fail-closed).")
    parser.add_argument("--allow-flag-off", action="store_true",
                        help="EVENT_SEMANTIC_ADJUDICATION_ENABLED off 여도 persist 허용(명시 우회).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # R-EventSinkDbTarget 가드(seed 와 동일 정책): 비-dev DB 는 명시 허용 없이 거부 → exit 1(자격증명 제외 라벨).
    try:
        label = assert_safe_write_target(
            app_env=settings.APP_ENV, database_url=settings.DATABASE_URL,
            allow_non_dev=ns.allow_non_dev_db)
    except UnsafeWriteTargetError as e:
        print(f"- BLOCKED unsafe write target: {e}")
        return 1
    print(f"- backfill target DB: {label} (APP_ENV={settings.APP_ENV})")

    after_ca: Optional[datetime] = None
    if ns.after_created_at:
        try:
            after_ca = datetime.fromisoformat(ns.after_created_at)
        except ValueError:
            print(f"- BLOCKED invalid --after-created-at (ISO8601 필요): {ns.after_created_at!r}")
            return 1

    try:
        out = asyncio.run(run_backfill_session(
            limit=ns.limit, after_link_id=ns.after_link_id, after_created_at=after_ca,
            cursor_mode=ns.cursor_mode, dry_run=ns.dry_run, allow_flag_off=ns.allow_flag_off))
    except Exception as e:   # runtime error → exit 2(자격증명 미노출: 타입·메시지만).
        print(f"- ERROR backfill runtime failure: {type(e).__name__}: {e}")
        return 2

    pre = out["preflight"]
    print(
        f"- preflight: ready_for_stage3={pre['ready_for_stage3']} current={pre['current_revision']} "
        f"behind={pre['behind_count']} flag_enabled={pre['flag_enabled']} persist_allowed={pre['persist_allowed']}"
    )
    if not out["ran"]:
        print(f"- BLOCKED backfill not run (block={out['block']}) — readiness/flag preflight 미충족·persist 안 함.")
        return decide_exit_code(out)
    report = out["report"]
    print(
        f"- backfill: dry_run={report['dry_run']} cursor_mode={report['cursor_mode']} limit={report['limit']} "
        f"after_link_id={report['after_link_id']} processed={report['processed']} "
        f"pending {report['pending_before']}->{report['pending_after']} by_status={report['by_status']} "
        f"next_cursor={report['next_cursor']} next_created_at={report['next_created_at']} "
        f"full_scan={report['full_scan']} event_count {report['event_count_before']}->{report['event_count_after']} "
        f"auto_merge={report['auto_merge_enabled']}"
    )
    return decide_exit_code(out)


if __name__ == "__main__":
    raise SystemExit(main())
