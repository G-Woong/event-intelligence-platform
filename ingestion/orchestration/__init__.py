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
    "SourceProfile",
    "load_source_profiles",
    "profiles_to_schedules",
    "is_live_eligible",
    "StrategyDecision",
    "decide_strategy",
    "load_last_run_state",
    "save_last_run_state",
    "record_last_run",
    # Phase D
    "ApiKeyReadiness",
    "audit_api_key_readiness",
    "summarize_readiness",
    "canonicalize_url",
    "ArticleCandidate",
    "parse_artifact_text",
    "BodyExtractionState",
    "assess_body_state",
    "assess_candidate_body",
    "CandidateExpansionReport",
    "expand_seed_to_article_candidates",
    "LiveSmokeResult",
    "audit_live_smoke",
    "summarize_live_smoke",
    # Phase D-P / E-0
    "SourceExpansionAudit",
    "audit_artifact_text",
    "audit_artifact_file",
    "summarize_expansion",
    "QualityPreGateResult",
    "evaluate_pre_gate",
    "normalize_published_at",
    "compute_duplicate_key",
    "assess_boilerplate",
    "summarize_pre_gate",
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
    "SourceProfile": "source_profile",
    "load_source_profiles": "source_profile",
    "profiles_to_schedules": "source_profile",
    "is_live_eligible": "source_profile",
    "StrategyDecision": "strategy_router",
    "decide_strategy": "strategy_router",
    "load_last_run_state": "cycle_state",
    "save_last_run_state": "cycle_state",
    "record_last_run": "cycle_state",
    # Phase D
    "ApiKeyReadiness": "api_readiness",
    "audit_api_key_readiness": "api_readiness",
    "summarize_readiness": "api_readiness",
    "canonicalize_url": "canonical_url",
    "ArticleCandidate": "article_candidate",
    "parse_artifact_text": "artifact_parser",
    "BodyExtractionState": "body_state",
    "assess_body_state": "body_state",
    "assess_candidate_body": "body_state",
    "CandidateExpansionReport": "seed_expansion",
    "expand_seed_to_article_candidates": "seed_expansion",
    "LiveSmokeResult": "live_smoke_audit",
    "audit_live_smoke": "live_smoke_audit",
    "summarize_live_smoke": "live_smoke_audit",
    # Phase D-P / E-0
    "SourceExpansionAudit": "production_audit",
    "audit_artifact_text": "production_audit",
    "audit_artifact_file": "production_audit",
    "summarize_expansion": "production_audit",
    "QualityPreGateResult": "quality_pre_gate",
    "evaluate_pre_gate": "quality_pre_gate",
    "normalize_published_at": "quality_pre_gate",
    "compute_duplicate_key": "quality_pre_gate",
    "assess_boilerplate": "quality_pre_gate",
    "summarize_pre_gate": "quality_pre_gate",
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
    from ingestion.orchestration.cycle_state import (  # noqa: F401
        load_last_run_state,
        record_last_run,
        save_last_run_state,
    )
    from ingestion.orchestration.run_orchestration_cycle import (  # noqa: F401
        DEFAULT_SOURCES,
        CycleReport,
        SourceOutcome,
        run_cycle,
    )
    from ingestion.orchestration.source_profile import (  # noqa: F401
        SourceProfile,
        load_source_profiles,
        profiles_to_schedules,
    )
    from ingestion.orchestration.strategy_router import (  # noqa: F401
        StrategyDecision,
        decide_strategy,
    )
