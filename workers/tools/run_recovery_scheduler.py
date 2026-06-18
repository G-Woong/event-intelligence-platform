from __future__ import annotations

"""복구 주기 드라이버 (Orchestration 하드닝, Phase 3).

수동 CLI(run_dlq_reaper, reconcile_stuck_once)를 하나의 **주기 구동 루프**로 묶는다. 매 tick마다:
  1) reconcile-stuck       : 큐에 enqueued 상태로 묶인 행 회수(HTTP admin API)
  2) requeue-failed-xadd   : PG는 됐으나 Redis XADD 실패한 xadd_failed 행 재발행(HTTP admin API)
  3) reap PEL              : worker crash 등으로 PEL에 남은 메시지 XAUTOCLAIM 회수→retry/DLQ(in-process)

각 action은 독립적으로 try/except로 격리되어, 하나가 실패해도 루프와 나머지 action은 계속된다.
우회/삭제 없음 — 보존+재처리만.

배포: 이 스크립트를 docker compose service 또는 cron(예: `--once`를 1분 간격)으로 띄운다.
  daemon:  python -m workers.tools.run_recovery_scheduler --interval-sec 60
  cron:    python -m workers.tools.run_recovery_scheduler --once

Env:
  BACKEND_INTERNAL_URL  default http://localhost:8000
  ADMIN_API_TOKEN       설정 시 X-Admin-Token 헤더로 전송(미설정이면 dev 모드 가정)
"""

import argparse
import logging
import os
import time
from typing import Callable

import httpx

from backend.app.db import redis as redis_db
from workers.queue import dlq

logger = logging.getLogger("recovery_scheduler")

Action = tuple[str, Callable[[], dict]]


def _admin_headers() -> dict[str, str]:
    token = os.getenv("ADMIN_API_TOKEN", "")
    return {"X-Admin-Token": token} if token else {}


def _backend_url(path: str) -> str:
    base = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8000").rstrip("/")
    return f"{base}{path}"


def reconcile_stuck_action(before_seconds: int, limit: int, dry_run: bool) -> dict:
    resp = httpx.post(
        _backend_url("/api/admin/raw-events/reconcile-stuck"),
        json={"before_seconds": before_seconds, "limit": limit, "dry_run": dry_run},
        headers=_admin_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def requeue_failed_xadd_action(limit: int, max_retries: int, dry_run: bool) -> dict:
    resp = httpx.post(
        _backend_url("/api/admin/raw-events/requeue-failed-xadd"),
        json={"limit": limit, "max_requeue": max_retries, "dry_run": dry_run},
        headers=_admin_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def reap_pending_action(
    stream: str, group: str, consumer: str, min_idle_ms: int, dlq_stream: str, max_retries: int
) -> dict:
    redis_db.ensure_group(stream, group)
    client = redis_db.get_redis()
    return dlq.reap_pending(
        client, stream, group, consumer, min_idle_ms, dlq_stream, max_retries=max_retries
    )


def run_recovery_cycle(actions: list[Action]) -> dict[str, object]:
    """각 action을 격리 실행한다. 반환: {name: result|{"error": ...}}. 예외는 루프를 죽이지 않는다."""
    results: dict[str, object] = {}
    for name, fn in actions:
        try:
            results[name] = fn()
            logger.info("recovery action ok name=%s result=%s", name, results[name])
        except Exception as exc:  # 한 action 실패가 다른 action/루프를 중단시키지 않음
            results[name] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            logger.warning("recovery action failed name=%s error=%s", name, results[name])
    return results


def _build_actions(args) -> list[Action]:
    return [
        ("reconcile_stuck", lambda: reconcile_stuck_action(args.before_seconds, args.limit, args.dry_run)),
        ("requeue_failed_xadd", lambda: requeue_failed_xadd_action(args.limit, args.max_retries, args.dry_run)),
        (
            "reap_pending",
            lambda: reap_pending_action(
                args.stream, args.group, args.consumer, args.min_idle_ms, args.dlq_stream, args.max_retries
            ),
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="주기 복구 드라이버(reconcile + requeue-failed-xadd + PEL reap)")
    parser.add_argument("--interval-sec", type=int, default=60, help="tick 간격(초). --once면 무시")
    parser.add_argument("--once", action="store_true", help="1회만 실행하고 종료(cron/CI용)")
    parser.add_argument("--dry-run", action="store_true", help="HTTP 복구 action을 dry-run으로")
    parser.add_argument("--before-seconds", type=int, default=600)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--stream", default="stream:raw_events")
    parser.add_argument("--group", default="group:ingest")
    parser.add_argument("--consumer", default="recovery-scheduler-1")
    parser.add_argument("--min-idle-ms", type=int, default=60000)
    parser.add_argument("--max-retries", type=int, default=dlq.DEFAULT_MAX_RETRIES)
    parser.add_argument("--dlq-stream", default="stream:raw_events:dlq")
    args = parser.parse_args(argv)

    actions = _build_actions(args)
    while True:
        results = run_recovery_cycle(actions)
        if args.once:
            # 모든 action이 실패하면 cron이 성공으로 오인하지 않도록 non-zero 반환.
            all_failed = bool(results) and all(
                isinstance(r, dict) and "error" in r for r in results.values()
            )
            return 1 if all_failed else 0
        time.sleep(max(1, args.interval_sec))


if __name__ == "__main__":
    raise SystemExit(main())
