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
REQUIRES_OFFICIAL_API_OR_CONTRACT = "requires_official_api_or_contract"
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
    # Phase G-2: dcinside는 robots(User-agent:*) 허용 갤러리 static fetch로 복구됨(우회 0) →
    # 더 이상 disable 대상이 아님(decide_source_value→None=keep_active). 상세는 dcinside_strategy.py.
    "google_trends_explore": SourceValueDecision(
        "google_trends_explore", REQUIRES_OFFICIAL_API_OR_CONTRACT,
        "no official Google Trends API; pytrends unofficial+absent; explore endpoint anti-abuse 429 "
        "(no-bypass); trending covered by google_trending_now → requires official API/contract",
        {"enabled": False, "profile_status": "disabled",
         "skip_reason": "requires_official_api_or_contract",
         "readiness_status": "REQUIRES_OFFICIAL_API_OR_CONTRACT"},
    ),
}


def decide_source_value(source_id: str) -> Optional[SourceValueDecision]:
    """source_id → SourceValueDecision. 미등록이면 None(=keep_active 후보)."""
    return _VALUE_DECISIONS.get(source_id)


def is_disabled_decision(decision: Optional[SourceValueDecision]) -> bool:
    return decision is not None and decision.decision in (
        DISABLE_NOT_SERVICE_USEFUL, POLICY_EXCLUDED, NEEDS_API_INTEGRATION,
        REQUIRES_OFFICIAL_API_OR_CONTRACT,
    )


def all_value_decisions() -> dict[str, SourceValueDecision]:
    return dict(_VALUE_DECISIONS)
