"""Phase A deterministic ingestion orchestration.

설계 출처: docs/Orchestration_Construction (00 §7.1 Final implementation stance,
07 노드 설계, 11 구현 청사진). Layer 1 = 결정적 수집 cycle, 신규 설치 0.
"""
from ingestion.orchestration.event_seed import SUCCESS_STATUSES, to_event_seed
from ingestion.orchestration.run_orchestration_cycle import (
    DEFAULT_SOURCES,
    CycleReport,
    SourceOutcome,
    run_cycle,
)

__all__ = [
    "run_cycle",
    "CycleReport",
    "SourceOutcome",
    "DEFAULT_SOURCES",
    "to_event_seed",
    "SUCCESS_STATUSES",
]
