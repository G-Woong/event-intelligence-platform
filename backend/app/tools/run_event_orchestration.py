"""D-1 — 운영 결선 composition root: 주기 수집 → Event 타임라인 영속.

**왜 backend 측에 있나(decoupling 불변식):** ingestion 런타임은 backend 를 import 하지 않는다.
backend→ingestion 은 허용 방향이므로(`event_ingest_pipeline` 이 유일 브리지), 운영 자동 경로에서
Event sink 를 **만들어 주입하는 composition root 는 backend 에 둔다**. 이 모듈은 ingestion 의
`run_production_orchestration.main()` 을 import(허용)해 그대로 재사용하되, 그 주입 seam
(`event_resolution_sink=`)에 backend-bound sink 를 끼운다. `ingestion/tools/` 는 무변경
(backend-free 유지). — ADR#23.

흐름:
    backend CLI(이 모듈)
      → 전용 NullPool async engine + async_sessionmaker (생명주기 = 이 모듈 소유)
      → make_orchestration_event_sink(factory)            (EVENT_RESOLUTION_ENABLED / --event-resolution)
      → ingestion run_production_orchestration.main(rest, event_resolution_sink=sink)
          → source collection → cross_source_dedup → sink → event_ingest_pipeline
          → event_resolution_pipeline → events / event_updates / cluster_event_map / event_links
      → engine.dispose()                                   (finally — 자원 정리)

설계 결정:
  - **전용 NullPool 엔진:** API 서버용 module-global 풀 엔진(`db/postgres.py`)을 재사용하지 않고
    배치 전용 엔진을 따로 만든다. sink 가 sync 경계에서 `asyncio.run` 으로 호출되므로(호출당 loop
    1개), NullPool 은 loop 간 커넥션 재사용/누수를 차단한다(checkout→close 가 같은 loop 안에서 끝남).
  - **flag 게이트(off-by-default):** `EVENT_RESOLUTION_ENABLED`(기본 false) 또는 `--event-resolution`
    중 하나라도 켜지면 sink 주입. 둘 다 꺼지면 sink=None → ingestion 기존 동작과 byte-identical.
  - **LLM 0 / network 0(Event path):** sink 경로는 결정론(record 필드만). 수집 probe 의 외부 호출은
    기존과 동일(이 모듈이 새로 추가하는 외부 호출 없음).
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from typing import Callable, Iterator, Optional

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.config import settings
from backend.app.services.event_ingest_pipeline import make_orchestration_event_sink
from ingestion.tools.run_production_orchestration import main as ingestion_main


def _target_db_label() -> str:
    """settings.DATABASE_URL 의 host:port/dbname 만(자격증명 제외) — 운영/테스트 DB 혼동 방어 표시."""
    try:
        u = make_url(settings.DATABASE_URL)
        return f"{u.host or '?'}:{u.port or '?'}/{u.database or '?'}"
    except Exception:
        return "?"


@contextlib.contextmanager
def event_resolution_sink_cm(*, enabled: Optional[bool] = None) -> Iterator[Optional[Callable]]:
    """배치 전용 Event sink 생성 + 엔진 생명주기 소유(컨텍스트 종료 시 dispose).

    enabled=None 이면 `settings.EVENT_RESOLUTION_ENABLED`. off 면 엔진을 만들지 않고 None 을
    yield(DB 미접근 — ingestion 기존 동작 보존). on 이면 전용 NullPool 엔진 + sessionmaker 로 sink 를
    만들어 yield 하고, 종료 시 `engine.dispose()`(NullPool 이라 사실상 no-op, lifecycle 명시).
    """
    flag = settings.EVENT_RESOLUTION_ENABLED if enabled is None else enabled
    if not flag:
        yield None
        return

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        # enabled=True 강제: 이미 게이트를 통과했으므로 sink 내부에서 재검사하지 않는다.
        yield make_orchestration_event_sink(factory, enabled=True)
    finally:
        asyncio.run(engine.dispose())


def run_event_orchestration(
    argv: Optional[list[str]] = None, *, enabled: Optional[bool] = None
) -> int:
    """Event sink 를 주입해 ingestion production orchestration 을 1회 실행. exit code 반환.

    argv 는 ingestion CLI 인자(--mode/--all-due/--raw-events-sink/... 그대로). enabled 가 None 이면
    settings 를 따른다. sink 는 backend 가 소유·주입하고 ingestion 은 Callable 만 받는다(decoupling).
    """
    flag = settings.EVENT_RESOLUTION_ENABLED if enabled is None else enabled
    with event_resolution_sink_cm(enabled=flag) as sink:
        if sink is not None:
            # 운영/테스트 DB 혼동 방어: 어느 DB 로 Event 를 쓰는지 명시(자격증명 제외).
            print(f"- event_resolution: ON → target DB {_target_db_label()} (수집 후보 → events/event_updates)")
        else:
            print("- event_resolution: OFF (sink 미주입 — event_cards 경로만, 기존 동작)")
        return ingestion_main(argv, event_resolution_sink=sink)


def main(argv: Optional[list[str]] = None) -> int:
    """backend CLI 진입점. `--event-resolution` 만 자체 소비하고 나머지는 ingestion CLI 로 위임."""
    raw = list(sys.argv[1:] if argv is None else argv)
    # allow_abbrev=False: `--event-resolution` 의 축약(`--event-res`)이나 ingestion 의 미래
    # `--event-*` 옵션을 pre-parser 가 silent 하게 가로채지 않도록(arch R1).
    pre = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    pre.add_argument(
        "--event-resolution", action="store_true",
        help="수집 후보를 Event 타임라인으로 영속(EVENT_RESOLUTION_ENABLED 대체 트리거).",
    )
    ns, rest = pre.parse_known_args(raw)
    enabled = bool(ns.event_resolution) or settings.EVENT_RESOLUTION_ENABLED
    return run_event_orchestration(rest, enabled=enabled)


if __name__ == "__main__":
    raise SystemExit(main())
