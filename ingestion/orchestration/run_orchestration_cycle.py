from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

from ingestion.fetch_strategies.collection_probe import run_collection_probe
from ingestion.fetch_strategies.models import CollectionProbeResult
from ingestion.orchestration.event_seed import SUCCESS_STATUSES, to_event_seed
from ingestion.pipeline.event_queue import EventQueue

logger = logging.getLogger("ingestion.orchestration.run_orchestration_cycle")

# Phase A 최소 기본 소스 (문서 완료조건: gdelt + yna).
# 정식 소스 선정/주기 bucket(due 판정)은 Phase C(SourceProfile)에서 확장한다.
DEFAULT_SOURCES: tuple[str, ...] = ("gdelt", "yna")

ProbeFn = Callable[..., CollectionProbeResult]


@dataclass
class SourceOutcome:
    """한 소스의 1회 수집 결과 요약."""
    source_id: str
    status: str
    items_found: int
    enqueued: bool
    item_id: Optional[str] = None
    error_category: Optional[str] = None
    error: Optional[str] = None  # cycle 내부 예외 메시지(소스 격리 시)


@dataclass
class CycleReport:
    """1 cycle 실행 요약. JSONL/로그로 산출(dashboard는 후순위, D-11)."""
    cycle_id: str
    started_at: str
    ended_at: str
    sources_attempted: int
    sources_succeeded: int
    sources_failed: int
    items_enqueued: int
    outcomes: list[SourceOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "sources_attempted": self.sources_attempted,
            "sources_succeeded": self.sources_succeeded,
            "sources_failed": self.sources_failed,
            "items_enqueued": self.items_enqueued,
            "outcomes": [vars(o) for o in self.outcomes],
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cycle(
    sources: Sequence[str] | None = None,
    *,
    queue: EventQueue | None = None,
    probe_fn: ProbeFn = run_collection_probe,
    query: Optional[str] = None,
    max_items: int = 5,
    force: bool = False,
) -> CycleReport:
    """Phase A deterministic local orchestration cycle.

    각 소스를 ``run_collection_probe``로 1회 수집하고, 성공(LIVE_SUCCESS/PARTIAL) 결과를
    EventSeedCandidate로 EventQueue(JSONL)에 적재한다. 설계 원칙:

    - **소스 격리**: 한 소스의 실패/예외가 다른 소스를 막지 않는다(per-source try/except).
    - **probe 경유만**: 모든 네트워크 호출은 ``probe_fn``(=run_collection_probe) 경유.
      직접 httpx/playwright 호출 없음 → provider 우회 구조적 차단.
    - **no bypass**: ``force=False``(기본)는 health gate(쿨다운/격리/차단)를 존중한다.
    - **실패 비적재**: 성공만 큐에 넣고 실패는 CycleReport에만 기록(다운스트림 오염 방지).
      health store 갱신은 run_collection_probe 내부(_update_health)가 이미 수행한다.

    ``probe_fn``/``queue``는 주입 가능 → 단위 테스트는 fake로 결정적 검증.
    """
    src = tuple(sources) if sources is not None else DEFAULT_SOURCES
    q = queue if queue is not None else EventQueue()
    cycle_id = str(uuid.uuid4())
    started = _now_iso()
    outcomes: list[SourceOutcome] = []
    enqueued_count = 0
    succeeded = 0
    failed = 0

    for source_id in src:
        try:
            result = probe_fn(source_id, query=query, max_items=max_items, force=force)
            if result.status in SUCCESS_STATUSES:
                seed = to_event_seed(
                    result, query=query, cycle_id=cycle_id, timestamp=_now_iso()
                )
                item_id = q.enqueue(seed)
                succeeded += 1
                enqueued_count += 1
                outcomes.append(SourceOutcome(
                    source_id=source_id, status=result.status,
                    items_found=result.items_found, enqueued=True,
                    item_id=item_id, error_category=result.error_category,
                ))
            else:
                failed += 1
                outcomes.append(SourceOutcome(
                    source_id=source_id, status=result.status,
                    items_found=result.items_found, enqueued=False,
                    error_category=result.error_category,
                ))
        except Exception as exc:  # 소스 격리: probe/enqueue 예외가 cycle을 중단시키지 않음
            logger.warning("source %s failed during cycle: %s", source_id, exc)
            failed += 1
            outcomes.append(SourceOutcome(
                source_id=source_id, status="CYCLE_ERROR",
                items_found=0, enqueued=False, error=str(exc),
            ))

    report = CycleReport(
        cycle_id=cycle_id, started_at=started, ended_at=_now_iso(),
        sources_attempted=len(src), sources_succeeded=succeeded,
        sources_failed=failed, items_enqueued=enqueued_count, outcomes=outcomes,
    )
    logger.info(
        "cycle %s: attempted=%d succeeded=%d failed=%d enqueued=%d",
        cycle_id, len(src), succeeded, failed, enqueued_count,
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """CLI smoke: ``python -m ingestion.orchestration.run_orchestration_cycle [source...]``.

    실제 네트워크를 호출한다(live). pytest 회귀에는 포함하지 않는다(비결정성/rate-limit).
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Phase A deterministic collection cycle (live smoke)"
    )
    parser.add_argument("sources", nargs="*", help="source ids (default: gdelt yna)")
    parser.add_argument("--query", default=None)
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    report = run_cycle(
        args.sources or None, query=args.query,
        max_items=args.max_items, force=args.force,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
