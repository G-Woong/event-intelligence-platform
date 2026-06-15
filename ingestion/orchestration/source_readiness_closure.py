"""Phase G-1/G-7 Source readiness gap matrix — 비-ready source별 근본원인/차단계층/복구계획.

Phase F의 ProductionSourceState 분포에서 production_ready가 아닌 non-excluded source를 모아
각각 (root_cause, blocking_layer, rescue_possible, rescue_plan, required_code_change,
final_required_status)를 산출한다. closure runner가 이 matrix를 소비해 source별 rescue를 실행한다.

stdlib만. 신규 설치 0. 네트워크 0(순수 분류).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from ingestion.orchestration.source_value_policy import decide_source_value
from ingestion.orchestration.vendor_api_routes import has_vendor_route

# blocking_layer enum
API_ROUTE = "API_ROUTE"
API_PARAMS = "API_PARAMS"
SCHEMA_ADAPTER = "SCHEMA_ADAPTER"
BODY_FETCH = "BODY_FETCH"
BROWSER_RENDER = "BROWSER_RENDER"
ENCODING = "ENCODING"
RATE_LIMIT = "RATE_LIMIT"
EVIDENCE_ANCHOR = "EVIDENCE_ANCHOR"
TIME_ANCHOR = "TIME_ANCHOR"
EVENTQUEUE_SCHEMA = "EVENTQUEUE_SCHEMA"
RAW_EVENTS_BRIDGE = "RAW_EVENTS_BRIDGE"
SOURCE_VALUE = "SOURCE_VALUE"
POLICY = "POLICY"

# production state(미-ready) → 기본 blocking_layer 추론
_STATUS_TO_LAYER = {
    "VENDOR_CONTRACT_REQUIRED": API_ROUTE,
    "EXTERNAL_API_ERROR": API_PARAMS,            # reason으로 세분화
    "EXTERNAL_RATE_LIMITED": RATE_LIMIT,
    "PRODUCTION_READY_DEGRADED": EVIDENCE_ANCHOR,
    "NOT_SERVICE_USEFUL": SOURCE_VALUE,
    "POLICY_BLOCKED_NO_BYPASS": POLICY,
    "NEEDS_OPERATOR_REVIEW": API_PARAMS,
    "QUARANTINED": RATE_LIMIT,
    "COOLDOWN": RATE_LIMIT,
    "DEAD_END_SKIPPED": SOURCE_VALUE,
}


@dataclass(frozen=True)
class SourceReadinessGap:
    source_id: str
    previous_status: str
    source_group: str
    expected_record_type: str
    root_cause: tuple[str, ...]
    blocking_layer: str
    rescue_possible: bool
    rescue_plan: tuple[str, ...]
    required_code_change: tuple[str, ...]
    final_required_status: str

    def to_dict(self) -> dict:
        return asdict(self)


_GROUP_RECORD_TYPE = {
    "news": "article_candidate", "official": "structured_signal", "domain": "structured_signal",
    "search": "search_result", "community": "community_signal",
    "market": "structured_signal", "trend": "structured_signal",
}


def _refine_layer(status: str, reason: Optional[str], source_id: str) -> str:
    """terminal_reason으로 blocking_layer 세분화."""
    r = (reason or "").upper()
    if status == "EXTERNAL_API_ERROR":
        if "RESULT_CODE" in r:
            return API_PARAMS            # kma
        if "HTTP_403" in r or "ANTI_BOT" in r:
            return API_ROUTE             # nyt 공식 API로 전환
        if "EXCERPT" in r or "NO_FULL_BODY" in r:
            return BODY_FETCH            # cnbc
    if status == "PRODUCTION_READY_DEGRADED":
        if "TIMESTAMP" in r and "URL" not in r:
            return TIME_ANCHOR
        return EVIDENCE_ANCHOR
    return _STATUS_TO_LAYER.get(status, API_PARAMS)


def build_readiness_gap(state, profile) -> SourceReadinessGap:
    """단일 ProductionSourceState → SourceReadinessGap."""
    sid = state.source_id
    grp = state.source_group
    reason = state.terminal_reason
    layer = _refine_layer(state.current_status, reason, sid)

    value_decision = decide_source_value(sid)
    rescue_plan: list[str] = []
    code_change: list[str] = []
    rescue_possible = True
    final = "PRODUCTION_READY"

    if value_decision is not None:
        # 서비스 가치 없음/정책 차단/통합 필요 → disable/exclude로 확정(우회 아님)
        layer = SOURCE_VALUE if value_decision.decision != "policy_excluded" else POLICY
        rescue_plan = ["disable_low_value", "reflect_in_source_profiles"]
        code_change = ["source_profiles.yaml", "source_value_policy.py"]
        rescue_possible = True
        final = ("DISABLED_NOT_SERVICE_USEFUL" if value_decision.decision == "disabled_not_service_useful"
                 else "DISABLED_NEEDS_API_INTEGRATION" if value_decision.decision == "disabled_needs_api_integration"
                 else "POLICY_EXCLUDED")
    elif layer == API_ROUTE and has_vendor_route(sid):
        rescue_plan = ["vendor_route_fix", "schema_adapter", "structured_signal_or_article", "eventqueue_raw_events"]
        code_change = ["vendor_api_routes.py"]
    elif layer == API_PARAMS and has_vendor_route(sid):
        rescue_plan = ["param_fix", "live_validate", "schema_adapter", "eventqueue_raw_events"]
        code_change = ["vendor_api_routes.py"]
    elif layer == API_ROUTE:
        # nyt: 공식 API route(vendor_api_routes에 등록됨)
        rescue_plan = ["official_api_route", "schema_adapter", "eventqueue_raw_events"]
        code_change = ["vendor_api_routes.py"]
    elif layer == BODY_FETCH:
        rescue_plan = ["body_ladder_fetch", "excerpt_promo_demote", "article_alive_or_partial", "eventqueue_raw_events"]
        code_change = ["body_rescue_ladder.py"]
    elif layer in (EVIDENCE_ANCHOR, TIME_ANCHOR):
        rescue_plan = ["source_adapter_anchor_fix", "stable_url_or_time", "promote_from_degraded"]
        code_change = ["source_adapters.py", "source_strategy_memory.yaml"]
    elif layer == RATE_LIMIT:
        rescue_plan = ["rate_limit_cooldown_probe", "single_live_validate", "cooldown_managed_ready"]
        code_change = ["rate_limit_governor(reuse)"]
    else:
        rescue_possible = False
        rescue_plan = ["manual_review"]

    root_cause = tuple(c for c in [reason] if c) or ("non_ready",)
    return SourceReadinessGap(
        source_id=sid, previous_status=state.current_status, source_group=grp,
        expected_record_type=_GROUP_RECORD_TYPE.get(grp, "article_candidate"),
        root_cause=root_cause, blocking_layer=layer, rescue_possible=rescue_possible,
        rescue_plan=tuple(rescue_plan), required_code_change=tuple(code_change),
        final_required_status=final,
    )


# excluded(영구 정책 제외) — gap 대상 아님
_EXCLUDED_STATES = frozenset({"POLICY_EXCLUDED"})
_READY_STATES = frozenset({"PRODUCTION_READY"})


def build_gap_matrix(states, profiles) -> list[SourceReadinessGap]:
    """ProductionSourceState 목록 → 비-ready non-excluded source의 gap matrix.

    PRODUCTION_READY와 POLICY_EXCLUDED(이미 enabled=false)는 제외. 나머지(degraded 포함)는 대상.
    """
    prof_by_id = {p.source_id: p for p in profiles}
    gaps: list[SourceReadinessGap] = []
    for s in states:
        if s.current_status in _READY_STATES or s.current_status in _EXCLUDED_STATES:
            continue
        gaps.append(build_readiness_gap(s, prof_by_id.get(s.source_id)))
    return gaps


def summarize_gaps(gaps) -> dict:
    gaps = list(gaps)
    by_layer: dict[str, int] = {}
    rescuable = 0
    for g in gaps:
        by_layer[g.blocking_layer] = by_layer.get(g.blocking_layer, 0) + 1
        if g.rescue_possible:
            rescuable += 1
    return {"targets": len(gaps), "rescuable": rescuable, "by_layer": dict(sorted(by_layer.items()))}
