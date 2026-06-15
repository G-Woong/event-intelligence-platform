"""Phase G-3 SourceCapability — source별 수집 능력 선언(전략 라우팅의 입력).

목적: source별 if-스파게티 대신, 각 source가 무엇을 지원하는지(list/detail/api/rss/
static/browser/key/rate-limit/policy 민감도)를 **선언적 능력**으로 표현한다. StrategyGraph가
이 능력을 읽어 적용 가능한 전략 노드만 구성하고, ToolPlan/EvidenceGate가 이를 강제한다.

이 모듈은 Phase G-3 target 4개(dcinside/culture_info/product_hunt/gdelt)를 우선 담는다.
일반화는 필요할 때만(over-engineering 금지). 네트워크 0, stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# policy_sensitivity 등급
POLICY_LOW = "low"          # 공식 open-data/공개 API(robots/ToS 우려 낮음)
POLICY_MEDIUM = "medium"    # 공개 API지만 provider rate-limit governance 필요
POLICY_HIGH = "high"        # robots/ToS/저작권/PII 민감(커뮤니티 등) — 보수적 수집


@dataclass(frozen=True)
class SourceCapability:
    source_id: str
    source_group: str
    expected_record_type: str
    supports_list: bool
    supports_detail: bool
    supports_api: bool
    supports_rss: bool
    supports_static_html: bool
    supports_browser_render: bool
    requires_key: bool
    rate_limit_policy_id: Optional[str]
    policy_sensitivity: str


# Phase G-3 target capabilities (실측 ground truth 반영).
_CAPABILITIES: dict[str, SourceCapability] = {
    # dcinside: robots 허용 갤러리 list는 static로 가능, detail 본문은 static에 부재(JS/이미지).
    # ToS 자동수집 미검증 → policy_sensitivity HIGH.
    "dcinside": SourceCapability(
        source_id="dcinside", source_group="community",
        expected_record_type="community_signal",
        supports_list=True, supports_detail=True, supports_api=False, supports_rss=False,
        supports_static_html=True, supports_browser_render=True, requires_key=False,
        rate_limit_policy_id="dcinside_host", policy_sensitivity=POLICY_HIGH,
    ),
    # culture_info: data.go.kr 공식 open API. period2(list) + detail2(seq→실 url). 키 필요.
    "culture_info": SourceCapability(
        source_id="culture_info", source_group="domain",
        expected_record_type="official_record",
        supports_list=True, supports_detail=True, supports_api=True, supports_rss=False,
        supports_static_html=False, supports_browser_render=False, requires_key=True,
        rate_limit_policy_id=None, policy_sensitivity=POLICY_LOW,
    ),
    # product_hunt: 공식 GraphQL API(bearer). 확장 쿼리로 실 url/createdAt. 키 필요.
    "product_hunt": SourceCapability(
        source_id="product_hunt", source_group="community",
        expected_record_type="community_signal",
        supports_list=True, supports_detail=False, supports_api=True, supports_rss=False,
        supports_static_html=False, supports_browser_render=False, requires_key=True,
        rate_limit_policy_id="product_hunt_host", policy_sensitivity=POLICY_LOW,
    ),
    # gdelt: 공개 DOC 2.0 API(키 불필요). provider rate-limit governance 필요.
    "gdelt": SourceCapability(
        source_id="gdelt", source_group="official",
        expected_record_type="official_record",
        supports_list=True, supports_detail=False, supports_api=True, supports_rss=False,
        supports_static_html=False, supports_browser_render=False, requires_key=False,
        rate_limit_policy_id="gdelt_host", policy_sensitivity=POLICY_MEDIUM,
    ),
}


def capability_for(source_id: str) -> Optional[SourceCapability]:
    """source_id의 능력 선언(없으면 None)."""
    return _CAPABILITIES.get(source_id)


def all_capabilities() -> tuple[SourceCapability, ...]:
    return tuple(_CAPABILITIES[k] for k in sorted(_CAPABILITIES))
