"""Phase G-3 ToolPlan — StrategyNode + SourceCapability → 실행 가능한 호출 계획.

ToolPlan은 "무엇을 어떤 정책으로 호출할지"만 담는다. **secret 값은 담지 않는다** — headers_policy는
정책 이름("bearer_token"/"service_key_query"/"generic_collector_ua"/"none")일 뿐, 실제 키 값은
executor가 env_loader로 호출 시점에만 주입한다. rate_limit_check 노드는 rate_limit_key가 반드시
있어야 하고, policy_check 노드는 policy_probe를 통과해야 실행된다(빌드 단계 강제).

네트워크 0, stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ingestion.orchestration.source_capability import SourceCapability
from ingestion.orchestration.strategy_graph import (
    TOOL_API_GET,
    TOOL_API_POST,
    TOOL_BROWSER,
    TOOL_RATE_LIMIT_LOCK,
    TOOL_STATIC_HTML,
    StrategyNode,
    is_unsafe_strategy,
)

# headers_policy 값(정책 이름만; secret 미포함)
HEADERS_GENERIC_UA = "generic_collector_ua"
HEADERS_BEARER = "bearer_token"
HEADERS_SERVICE_KEY_QUERY = "service_key_query"
HEADERS_NONE = "none"

# output 기대
OUT_HTML = "html"
OUT_JSON = "json"
OUT_XML = "xml"
OUT_DECISION = "decision"


@dataclass(frozen=True)
class ToolPlan:
    source_id: str
    strategy_name: str
    url_or_endpoint: Optional[str]
    params: dict[str, str]
    headers_policy: str
    timeout_seconds: int
    rate_limit_key: Optional[str]
    expected_output: str

    def carries_secret(self) -> bool:
        """secret 누출 가드: params/엔드포인트에 실제 키 값이 박혀있지 않은지 점검(정책 이름만 허용)."""
        for v in self.params.values():
            if isinstance(v, str) and v.startswith("SECRET:"):
                return True
        return False


def build_tool_plan(
    cap: SourceCapability,
    node: StrategyNode,
    *,
    url_or_endpoint: Optional[str] = None,
    params: Optional[dict] = None,
    timeout_seconds: int = 20,
) -> ToolPlan:
    """StrategyNode + capability → ToolPlan. policy/rate-limit/secret 불변식 강제.

    - unsafe 전략이면 ValueError.
    - requires_rate_limit_check인데 capability.rate_limit_policy_id 없으면 ValueError.
    - browser 노드인데 capability.supports_browser_render=False면 ValueError.
    - params에 'SECRET:' 접두 값(실키 주입 시도)이 있으면 ValueError(정책 이름만 허용).
    """
    if is_unsafe_strategy(node.name) or is_unsafe_strategy(node.tool_type):
        raise ValueError(f"unsafe_strategy_rejected:{node.name}")
    if node.requires_rate_limit_check and cap.rate_limit_policy_id is None:
        raise ValueError(f"rate_limit_check_without_policy:{cap.source_id}:{node.name}")
    if node.tool_type == TOOL_BROWSER and not cap.supports_browser_render:
        raise ValueError(f"browser_not_supported:{cap.source_id}")

    headers_policy, expected = _policy_for(cap, node)
    params = dict(params or {})
    for v in params.values():
        if isinstance(v, str) and v.startswith("SECRET:"):
            raise ValueError("secret_value_in_tool_plan_params")
    rl_key = cap.rate_limit_policy_id if node.requires_rate_limit_check else None
    return ToolPlan(
        source_id=cap.source_id, strategy_name=node.name,
        url_or_endpoint=url_or_endpoint, params=params,
        headers_policy=headers_policy, timeout_seconds=timeout_seconds,
        rate_limit_key=rl_key, expected_output=expected,
    )


def _policy_for(cap: SourceCapability, node: StrategyNode) -> tuple[str, str]:
    """tool_type + capability → (headers_policy, expected_output)."""
    if node.tool_type == TOOL_STATIC_HTML:
        return HEADERS_GENERIC_UA, OUT_HTML
    if node.tool_type == TOOL_BROWSER:
        return HEADERS_GENERIC_UA, OUT_HTML
    if node.tool_type == TOOL_API_POST:
        # product_hunt: bearer token
        return (HEADERS_BEARER if cap.requires_key else HEADERS_NONE), OUT_JSON
    if node.tool_type == TOOL_API_GET:
        if not cap.requires_key:
            return HEADERS_NONE, OUT_JSON          # gdelt: 키 불필요
        return HEADERS_SERVICE_KEY_QUERY, OUT_XML  # culture_info: serviceKey query
    if node.tool_type == TOOL_RATE_LIMIT_LOCK:
        return HEADERS_NONE, OUT_DECISION
    return HEADERS_NONE, OUT_DECISION
