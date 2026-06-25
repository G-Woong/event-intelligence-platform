from __future__ import annotations

"""semantic adjudication backfill 주기 드라이버 (ADR#51, R-LiveIdentityBacklog).

backend.app.tools.backfill_semantic_adjudications 의 수동 CLI 를 **주기 구동 루프**로 묶는다 —
run_recovery_scheduler 관용구 재사용(--interval-sec / --once / while True + time.sleep). 매 tick:
  preflight(safe-target + readiness ready_for_stage3 + flag EVENT_SEMANTIC_ADJUDICATION_ENABLED)
  → 충족 시 backfill(bounded --limit · cursor_mode=created_at 오래된 백로그 우선) → shadow adjudication 누적.
  **자동 병합 0**(read + adjudication upsert only · Event 불변).

**안전 기본값(상용 계약 — ADR#51 옵션 B: off-by-default · dry-run default · no production enable):**
  - **dry-run default** — persist 는 명시 `--persist` 필요(미지정이면 read-only 규모 산출만).
  - **bounded** — `--limit` 기본 100(full_scan 회피). 0/음수면 무제한(비권장).
  - **gated** — readiness/flag 미충족이면 persist 안 함(`--once`→exit 1 · interval→로그+계속 · 크래시 금지).
  - **미배선** — docker compose 가동 서비스로 추가하지 않는다(운영 DB 0003→0009 migration 전 가동 금지).
    운영 배선은 runbook(docs/2_ROADMAP/15_IMPLEMENTATION_ROADMAP) 의 post-upgrade 절차 — 이 스크립트는
    scheduler-ready 관용구일 뿐 **실가동 0**.

**동시성(ADR#51 §6):** 단일 instance 가정(docker restart = 1 컨테이너). 동시 backfill 은 데이터 안전(link_id PK
upsert · 중복행 0)하나 **중복 work 가능** — advisory lock 미구현. 단일 runner / disjoint `--after-*` 로 운영.

**exit code(--once):** backfill CLI 와 공유(decide_exit_code) — 0=성공 · 1=blocked(readiness/flag) · 2=runtime
error · 3=dry-run 인데 pending 남음. interval 모드는 종료하지 않고 매 tick 결과를 로깅한다.

배포(미가동 · runbook 예시):
  cron:    python -m workers.tools.run_semantic_backfill_scheduler --once --persist --limit 100
  daemon:  python -m workers.tools.run_semantic_backfill_scheduler --interval-sec 300 --persist --limit 100
"""

import argparse
import asyncio
import logging
import sys
import time
from typing import Optional

from backend.app.core.config import settings
from backend.app.tools import backfill_semantic_adjudications as bf
from backend.app.tools.db_target import UnsafeWriteTargetError, assert_safe_write_target

logger = logging.getLogger("semantic_backfill_scheduler")


def _run_cycle(*, limit: Optional[int], cursor_mode: str, persist: bool, allow_flag_off: bool) -> dict:
    """1 tick: preflight + backfill(자체 엔진·NullPool). 예외 격리는 호출자(루프 보존)."""
    return asyncio.run(bf.run_backfill_session(
        limit=limit, cursor_mode=cursor_mode, dry_run=not persist, allow_flag_off=allow_flag_off))


def _log_cycle(out: dict) -> None:
    """tick 결과를 운영 관측 가능하게 로깅(secret/본문 비포함 — 카운트/플래그만)."""
    pre = out.get("preflight", {})
    if not out.get("ran"):
        logger.warning(
            "backfill cycle BLOCKED block=%s ready_for_stage3=%s flag_enabled=%s persist_allowed=%s",
            out.get("block"), pre.get("ready_for_stage3"), pre.get("flag_enabled"), pre.get("persist_allowed"))
        return
    rep = out["report"]
    logger.info(
        "backfill cycle ran dry_run=%s cursor_mode=%s processed=%s pending %s->%s by_status=%s "
        "full_scan=%s next_cursor=%s event_count %s->%s auto_merge=%s",
        rep["dry_run"], rep["cursor_mode"], rep["processed"], rep["pending_before"], rep["pending_after"],
        rep["by_status"], rep["full_scan"], rep["next_cursor"], rep["event_count_before"],
        rep["event_count_after"], rep["auto_merge_enabled"])


def main(argv: Optional[list[str]] = None) -> int:
    try:  # Windows cp949 콘솔이 한국어/em-dash 에 죽지 않도록 utf-8(closeout_sig 선례).
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="semantic adjudication backfill 주기 드라이버 (preflight gated·dry-run default·자동 병합 0·ADR#51).")
    parser.add_argument("--interval-sec", type=int, default=300, help="tick 간격(초). --once면 무시.")
    parser.add_argument("--once", action="store_true", help="1회만 실행하고 종료(cron/CI용).")
    parser.add_argument("--limit", type=int, default=100,
                        help="tick 당 bounded chunk 상한(full_scan 회피). 0/음수면 무제한(비권장).")
    parser.add_argument("--cursor-mode", choices=("id", "created_at"), default="created_at",
                        help="created_at=오래된 백로그 우선(배치 간 정확·동일 배치 내 임의·인덱스 없음·default)·id=UUIDv4 byte 순서.")
    parser.add_argument("--persist", action="store_true",
                        help="adjudication 영속(미지정=dry-run default·no production enable).")
    parser.add_argument("--allow-non-dev-db", action="store_true",
                        help="APP_ENV=staging/production DB 에도 허용(기본 거부·fail-closed).")
    parser.add_argument("--allow-flag-off", action="store_true",
                        help="EVENT_SEMANTIC_ADJUDICATION_ENABLED off 여도 persist 허용(명시 우회).")
    parser.add_argument("--log-level", default="INFO", help="로그 레벨(기본 INFO).")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # safe-target 가드(write DB) — fail-fast(unsafe 면 scheduler 시작 안 함·dry-run 도 일관 차단).
    try:
        label = assert_safe_write_target(
            app_env=settings.APP_ENV, database_url=settings.DATABASE_URL,
            allow_non_dev=args.allow_non_dev_db)
    except UnsafeWriteTargetError as e:
        logger.error("BLOCKED unsafe write target: %s", e)
        return 1
    limit: Optional[int] = args.limit if (args.limit and args.limit > 0) else None
    logger.info(
        "semantic backfill scheduler start target=%s APP_ENV=%s once=%s interval=%ss persist=%s "
        "cursor_mode=%s limit=%s", label, settings.APP_ENV, args.once, args.interval_sec, args.persist,
        args.cursor_mode, limit)

    while True:
        try:
            out = _run_cycle(limit=limit, cursor_mode=args.cursor_mode,
                             persist=args.persist, allow_flag_off=args.allow_flag_off)
            _log_cycle(out)
            code = bf.decide_exit_code(out)
        except Exception as exc:   # 한 tick 실패가 루프를 죽이지 않음(interval 자가복구); --once 면 exit 2.
            logger.warning("backfill cycle error %s: %s", type(exc).__name__, str(exc)[:200])
            code = 2
        if args.once:
            return code
        time.sleep(max(1, args.interval_sec))


if __name__ == "__main__":
    raise SystemExit(main())
