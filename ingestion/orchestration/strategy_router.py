from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ingestion.orchestration.source_profile import (
    COMMUNITY_DEFAULT_CONFIRMATION,
    SourceProfile,
)

# Phase C StrategyRouter(최소): 소스 프로필 → 수집 메타 결정(read-only metadata).
# 실제 수집 라우팅/재시도는 run_collection_probe가 책임진다(이 모듈은 대체하지 않는다).


@dataclass(frozen=True)
class StrategyDecision:
    source_id: str
    purpose: str
    preferred_strategy: Optional[str]
    confirmation_policy: str
    risk_level: str
    should_enqueue_success: bool


def decide_strategy(profile: SourceProfile) -> StrategyDecision:
    """SourceProfile → StrategyDecision (순수 함수, side effect 없음).

    정책:
    - disabled 소스는 should_enqueue_success=False (cycle은 보통 schedule 단계에서 이미 제외).
    - community 소스는 confirmation_policy를 unconfirmed 계열로 보장한다(단독 확정 금지, 09 D-9).
      yaml에서 standard로 남았더라도 보수적으로 보정한다.
    - preferred_strategy는 강제 경로가 아니라 metadata로 그대로 전달(None 안정 처리).
    """
    policy = profile.confirmation_policy
    if profile.is_community and policy == "standard":
        policy = COMMUNITY_DEFAULT_CONFIRMATION

    return StrategyDecision(
        source_id=profile.source_id,
        purpose=profile.purpose,
        preferred_strategy=profile.preferred_strategy,
        confirmation_policy=policy,
        risk_level=profile.risk_level,
        should_enqueue_success=profile.enabled,
    )
