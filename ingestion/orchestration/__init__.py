"""Phase A/B deterministic ingestion orchestration.

설계 출처: docs/Orchestration_Construction (00 §7.1 Final implementation stance,
07 노드 설계, 11 구현 청사진). Layer 1 = 결정적 수집 cycle, 신규 설치 0.

심볼은 PEP 562 lazy import로 노출한다. 이유: ``__init__``이 실행 모듈
``run_orchestration_cycle``을 즉시 import하면
``python -m ingestion.orchestration.run_orchestration_cycle`` 실행 시 runpy가
"이미 sys.modules에 있다"는 RuntimeWarning을 낸다. lazy 노출로 공개 API는
유지하면서 그 경고를 제거한다.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

__all__ = [
    "run_cycle",
    "CycleReport",
    "SourceOutcome",
    "DEFAULT_SOURCES",
    "to_event_seed",
    "SUCCESS_STATUSES",
    "SourceSchedule",
    "is_due",
    "select_due_sources",
]

_SYMBOL_MODULE = {
    "run_cycle": "run_orchestration_cycle",
    "CycleReport": "run_orchestration_cycle",
    "SourceOutcome": "run_orchestration_cycle",
    "DEFAULT_SOURCES": "run_orchestration_cycle",
    "to_event_seed": "event_seed",
    "SUCCESS_STATUSES": "event_seed",
    "SourceSchedule": "cycle_planner",
    "is_due": "cycle_planner",
    "select_due_sources": "cycle_planner",
}


def __getattr__(name: str):
    module = _SYMBOL_MODULE.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"{__name__}.{module}"), name)


def __dir__() -> list[str]:
    return sorted(__all__)


if TYPE_CHECKING:  # 정적 분석/IDE 자동완성용 (런타임 import 아님)
    from ingestion.orchestration.cycle_planner import (  # noqa: F401
        SourceSchedule,
        is_due,
        select_due_sources,
    )
    from ingestion.orchestration.event_seed import (  # noqa: F401
        SUCCESS_STATUSES,
        to_event_seed,
    )
    from ingestion.orchestration.run_orchestration_cycle import (  # noqa: F401
        DEFAULT_SOURCES,
        CycleReport,
        SourceOutcome,
        run_cycle,
    )
