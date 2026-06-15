"""Phase G-3 StrategyGraph — SourceCapability → 정책 안전 전략 노드 그래프.

source별 if-분기 대신, capability를 읽어 적용 가능한 전략 노드(StrategyNode)와 fallback 간선을
구성한다. 각 노드는 policy/rate-limit 체크 요구와 success_criteria를 선언한다. unsafe 전략
(proxy rotation / captcha solver / robots ignore / rate-limit ignore 등)은 그래프에 **들어올 수
없다**(빌드시 reject). LLM supervisor가 제안하더라도 allowed registry 밖이면 거부된다.

네트워크 0, stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ingestion.orchestration.source_capability import (
    POLICY_HIGH,
    SourceCapability,
)

# 절대 허용하지 않는 전략(우회). 그래프 빌드/LLM 제안 양쪽에서 reject.
UNSAFE_STRATEGIES: frozenset[str] = frozenset({
    "proxy_rotation", "captcha_solver", "robots_ignore", "ignore_rate_limit",
    "rate_limit_ignore", "login_bypass", "paywall_bypass", "anti_bot_evasion",
    "header_spoofing_to_evade_block", "tor_exit_rotation", "user_agent_rotation_to_evade",
})

# tool_type enum(ToolPlan executor가 해석)
TOOL_STATIC_HTML = "static_html"
TOOL_API_GET = "api_get"
TOOL_API_POST = "api_post"
TOOL_BROWSER = "browser_render"
TOOL_RATE_LIMIT_LOCK = "rate_limit_lock"
TOOL_ADAPTER = "adapter"
TOOL_EVIDENCE_GATE = "evidence_gate"


@dataclass(frozen=True)
class StrategyNode:
    name: str
    tool_type: str
    allowed_record_types: tuple[str, ...]
    requires_policy_check: bool
    requires_rate_limit_check: bool
    max_attempts_per_run: int
    success_criteria: tuple[str, ...]


@dataclass(frozen=True)
class StrategyGraph:
    source_id: str
    nodes: tuple[StrategyNode, ...]
    fallback_edges: dict[str, tuple[str, ...]]

    def node(self, name: str) -> Optional[StrategyNode]:
        for n in self.nodes:
            if n.name == name:
                return n
        return None


def is_unsafe_strategy(name: str) -> bool:
    return name in UNSAFE_STRATEGIES


def reject_unsafe(names) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """전략명 목록 → (safe, rejected). LLM 제안 필터링 진입점."""
    safe, rejected = [], []
    for n in names:
        (rejected if is_unsafe_strategy(n) else safe).append(n)
    return tuple(safe), tuple(rejected)


def _dcinside_graph(cap: SourceCapability) -> StrategyGraph:
    rt = (cap.expected_record_type,)
    nodes = (
        StrategyNode("robots_allowed_list_fetch", TOOL_STATIC_HTML, rt, True, True, 1,
                     ("http_200", "no_block_marker", "list_rows_parsed")),
        StrategyNode("list_to_detail_url_extract", TOOL_STATIC_HTML, rt, True, False, 1,
                     ("detail_urls_found",)),
        StrategyNode("detail_policy_probe", TOOL_STATIC_HTML, rt, True, True, 1,
                     ("robots_allows_detail", "no_block_marker")),
        StrategyNode("detail_static_fetch", TOOL_STATIC_HTML, rt, True, True, 1,
                     ("http_200",)),
        StrategyNode("detail_body_selector_extract", TOOL_ADAPTER, rt, False, False, 1,
                     ("body_non_empty",)),
        # fallback: 본문 불가 시 list-level community_signal(preview only) 유지
        StrategyNode("community_signal_list_preview", TOOL_ADAPTER, rt, False, False, 1,
                     ("list_records_with_external_url",)),
        StrategyNode("evidence_gate", TOOL_EVIDENCE_GATE, rt, False, False, 1,
                     ("evidence_gate_evaluated",)),
    )
    edges = {
        "detail_body_selector_extract": ("community_signal_list_preview",),
        "detail_static_fetch": ("community_signal_list_preview",),
        "detail_policy_probe": ("community_signal_list_preview",),
    }
    return StrategyGraph(cap.source_id, nodes, edges)


def _culture_info_graph(cap: SourceCapability) -> StrategyGraph:
    rt = (cap.expected_record_type,)
    nodes = (
        StrategyNode("api_list_fetch", TOOL_API_GET, rt, False, False, 1, ("http_200", "items_parsed")),
        StrategyNode("seq_extract", TOOL_ADAPTER, rt, False, False, 1, ("stable_seq_found",)),
        StrategyNode("api_detail_fetch", TOOL_API_GET, rt, False, False, 1, ("http_200", "detail_url_field")),
        StrategyNode("official_record_adapter", TOOL_ADAPTER, rt, False, False, 1,
                     ("external_url", "time_anchor")),
        StrategyNode("evidence_gate", TOOL_EVIDENCE_GATE, rt, False, False, 1, ("evidence_gate_evaluated",)),
    )
    return StrategyGraph(cap.source_id, nodes, {})


def _product_hunt_graph(cap: SourceCapability) -> StrategyGraph:
    rt = (cap.expected_record_type,)
    nodes = (
        StrategyNode("api_graphql_fetch", TOOL_API_POST, rt, False, True, 1, ("http_200", "edges_parsed")),
        StrategyNode("real_url_createdAt_extract", TOOL_ADAPTER, rt, False, False, 1,
                     ("real_url", "real_createdAt")),
        StrategyNode("community_signal_adapter", TOOL_ADAPTER, rt, False, False, 1,
                     ("external_url", "time_anchor")),
        StrategyNode("evidence_gate", TOOL_EVIDENCE_GATE, rt, False, False, 1, ("evidence_gate_evaluated",)),
    )
    return StrategyGraph(cap.source_id, nodes, {})


def _gdelt_graph(cap: SourceCapability) -> StrategyGraph:
    rt = (cap.expected_record_type,)
    nodes = (
        StrategyNode("host_rate_limit_lock", TOOL_RATE_LIMIT_LOCK, rt, False, True, 1,
                     ("interval_respected_or_pending",)),
        StrategyNode("spaced_single_probe", TOOL_API_GET, rt, False, True, 3,
                     ("http_200", "articles_found")),
        StrategyNode("official_record_adapter", TOOL_ADAPTER, rt, False, False, 1, ("external_url",)),
        StrategyNode("evidence_gate", TOOL_EVIDENCE_GATE, rt, False, False, 1, ("evidence_gate_evaluated",)),
    )
    # fallback: 429면 pending_resume(terminal 아님)
    edges = {"spaced_single_probe": ("host_rate_limit_lock",)}
    return StrategyGraph(cap.source_id, nodes, edges)


_BUILDERS = {
    "dcinside": _dcinside_graph,
    "culture_info": _culture_info_graph,
    "product_hunt": _product_hunt_graph,
    "gdelt": _gdelt_graph,
}


def build_strategy_graph(cap: SourceCapability) -> StrategyGraph:
    """SourceCapability → StrategyGraph. unsafe 노드가 섞이면 ValueError(빌드 거부).

    rate_limit_policy_id가 없는데 rate-limit 체크를 요구하는 모순 노드도 거부한다.
    """
    builder = _BUILDERS.get(cap.source_id)
    if builder is None:
        raise ValueError(f"no_strategy_graph_for:{cap.source_id}")
    graph = builder(cap)
    for n in graph.nodes:
        if is_unsafe_strategy(n.name) or n.tool_type in UNSAFE_STRATEGIES:
            raise ValueError(f"unsafe_strategy_rejected:{n.name}")
        if n.requires_rate_limit_check and cap.rate_limit_policy_id is None:
            raise ValueError(f"rate_limit_check_without_policy:{cap.source_id}:{n.name}")
    # HIGH 민감 source는 detail 본문 노드가 fallback(preview-only)을 반드시 가져야 한다(보수성).
    if cap.policy_sensitivity == POLICY_HIGH and graph.node("detail_body_selector_extract"):
        if "detail_body_selector_extract" not in graph.fallback_edges:
            raise ValueError(f"high_sensitivity_detail_requires_fallback:{cap.source_id}")
    return graph
