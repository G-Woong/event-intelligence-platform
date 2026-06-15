"""Phase G-8 Source value policy — 서비스 가치 없는 source를 정직하게 disable로 확정.

production_ready로 억지로 포장하지 않는다. event intelligence에 쓸 수 없는 source(예: its의
per-link 교통 telemetry)는 disabled_not_service_useful로, 정책 차단(robots/login/paywall)은
policy_excluded로, 키 없음+probe 미연결은 needs_api_integration로 분류한다. 이 결정은
source_profiles.yaml에 반영되어 운영 runner가 더 이상 반복 probe하지 않게 한다.

stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# 최종 처리 분류
DISABLE_NOT_SERVICE_USEFUL = "disabled_not_service_useful"
POLICY_EXCLUDED = "policy_excluded"
NEEDS_API_INTEGRATION = "disabled_needs_api_integration"
KEEP_ACTIVE = "keep_active"


@dataclass(frozen=True)
class SourceValueDecision:
    source_id: str
    decision: str               # disabled_not_service_useful | policy_excluded | disabled_needs_api_integration | keep_active
    rationale: str
    profile_patch: dict         # source_profiles.yaml에 반영할 필드(enabled/profile_status/skip_reason 등)


# Phase G 결정(근거는 E-3/F 실측 + 정책)
_VALUE_DECISIONS = {
    "its": SourceValueDecision(
        "its", DISABLE_NOT_SERVICE_USEFUL,
        "per-link road-speed telemetry is not event-grade; aggregation has no commercial event value",
        {"enabled": False, "profile_status": "disabled", "skip_reason": "not_service_useful",
         "readiness_status": "DISABLED_LOW_VALUE"},
    ),
    "dcinside": SourceValueDecision(
        "dcinside", POLICY_EXCLUDED,
        "robots/policy block, no-bypass; community board excluded by policy",
        {"enabled": False, "profile_status": "disabled", "skip_reason": "robots_or_policy_block",
         "readiness_status": "MVP_EXCLUDED"},
    ),
    "google_trends_explore": SourceValueDecision(
        "google_trends_explore", NEEDS_API_INTEGRATION,
        "no API key + probe not wired (registry _SERVICE_CONFIGS missing) + rate-limited; "
        "requires operator API integration before re-enable",
        {"enabled": False, "profile_status": "disabled", "skip_reason": "needs_api_integration",
         "readiness_status": "MVP_DEFERRED"},
    ),
}


def decide_source_value(source_id: str) -> Optional[SourceValueDecision]:
    """source_id → SourceValueDecision. 미등록이면 None(=keep_active 후보)."""
    return _VALUE_DECISIONS.get(source_id)


def is_disabled_decision(decision: Optional[SourceValueDecision]) -> bool:
    return decision is not None and decision.decision in (
        DISABLE_NOT_SERVICE_USEFUL, POLICY_EXCLUDED, NEEDS_API_INTEGRATION,
    )


def all_value_decisions() -> dict[str, SourceValueDecision]:
    return dict(_VALUE_DECISIONS)
