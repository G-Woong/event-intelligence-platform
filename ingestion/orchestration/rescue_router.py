"""Phase G-3/G-9 RescueRouter — blocking_layer/source 특성 → rescue strategy 선택.

source_readiness_closure의 SourceReadinessGap을 받아 어떤 rescue strategy를 실행할지 결정한다.
closure runner가 이 RescueDecision을 보고 vendor route / body ladder / adapter fix / cooldown probe /
disable를 디스패치한다. 재실행에도 재사용 가능(결정적).

stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ingestion.orchestration.source_readiness_closure import (
    API_PARAMS,
    API_ROUTE,
    BODY_FETCH,
    BROWSER_RENDER,
    ENCODING,
    EVIDENCE_ANCHOR,
    POLICY,
    RATE_LIMIT,
    SCHEMA_ADAPTER,
    SOURCE_VALUE,
    TIME_ANCHOR,
)
from ingestion.orchestration.source_content_type import body_ladder_eligible

# rescue strategy 식별자
VENDOR_ROUTE_FIX = "vendor_route_fix"
PARAM_FIX = "param_fix"
ENCODING_FIX = "encoding_fix"
SOURCE_ADAPTER_FIX = "source_adapter_fix"
BODY_LADDER_FETCH = "body_ladder_fetch"
BROWSER_RENDER_SAFE = "browser_render_safe"
RATE_LIMIT_COOLDOWN_PROBE = "rate_limit_cooldown_probe"
STRUCTURED_SIGNAL_REDUCE = "structured_signal_reduce"
DISABLE_LOW_VALUE = "disable_low_value"
POLICY_BLOCK_NO_BYPASS = "policy_block_no_bypass"
MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class RescueDecision:
    source_id: str
    previous_status: str
    blocking_layer: str
    rescue_strategy: str
    allowed: bool
    reason: Optional[str]


_LAYER_TO_STRATEGY = {
    API_ROUTE: VENDOR_ROUTE_FIX,
    API_PARAMS: PARAM_FIX,
    SCHEMA_ADAPTER: SOURCE_ADAPTER_FIX,
    BODY_FETCH: BODY_LADDER_FETCH,
    BROWSER_RENDER: BROWSER_RENDER_SAFE,
    ENCODING: ENCODING_FIX,
    RATE_LIMIT: RATE_LIMIT_COOLDOWN_PROBE,
    EVIDENCE_ANCHOR: SOURCE_ADAPTER_FIX,
    TIME_ANCHOR: SOURCE_ADAPTER_FIX,
    SOURCE_VALUE: DISABLE_LOW_VALUE,
    POLICY: POLICY_BLOCK_NO_BYPASS,
}


def decide_rescue(gap) -> RescueDecision:
    """SourceReadinessGap → RescueDecision. 우회 불가(POLICY) source는 allowed=True지만
    rescue_strategy=policy_block_no_bypass(=정직 종결)로 둔다."""
    sid = gap.source_id
    strategy = _LAYER_TO_STRATEGY.get(gap.blocking_layer, MANUAL_REVIEW)

    # 콘텐츠 타입 게이트(source_content_type 라이브 배선): BODY_FETCH로 분류됐어도 산문 본문이
    # 없는 소스(카탈로그 메타데이터/구조화/검색)는 body ladder가 헛돈다 — 메타가 곧 완성 record다.
    # body_ladder_eligible=False면 structured_signal_reduce로(본문 추출 실패가 아니라 본문 비대상).
    if strategy == BODY_LADDER_FETCH and not body_ladder_eligible(sid, gap.source_group):
        strategy = STRUCTURED_SIGNAL_REDUCE

    # vendor route가 있는 source는 우회 없이 공식 route로 해결(API_ROUTE/PARAMS/RATE_LIMIT 포함).
    # 단 정책 차단/서비스 가치 없음(disable)은 vendor route보다 우선(억지로 살리지 않음).
    from ingestion.orchestration.vendor_api_routes import has_vendor_route
    if gap.blocking_layer not in (POLICY, SOURCE_VALUE) and has_vendor_route(sid):
        strategy = VENDOR_ROUTE_FIX

    allowed = gap.rescue_possible
    reason = None
    if strategy == POLICY_BLOCK_NO_BYPASS:
        reason = "policy_no_bypass_documented"
    elif strategy == DISABLE_LOW_VALUE:
        reason = "disable_reflected_in_profiles"
    elif strategy == MANUAL_REVIEW:
        allowed = False
        reason = "no_automatic_rescue_path"
    elif strategy == STRUCTURED_SIGNAL_REDUCE:
        reason = "metadata_complete_no_prose_body"

    return RescueDecision(
        source_id=sid, previous_status=gap.previous_status,
        blocking_layer=gap.blocking_layer, rescue_strategy=strategy,
        allowed=allowed, reason=reason,
    )


def route_all(gaps) -> list[RescueDecision]:
    return [decide_rescue(g) for g in gaps]
