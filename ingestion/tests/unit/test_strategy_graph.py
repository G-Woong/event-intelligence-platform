"""G-3: StrategyGraph — capability 기반 노드 구성 + unsafe 전략 거부."""
from __future__ import annotations

import pytest

from ingestion.orchestration.source_capability import capability_for
from ingestion.orchestration.strategy_graph import (
    UNSAFE_STRATEGIES,
    build_strategy_graph,
    is_unsafe_strategy,
    reject_unsafe,
)


def test_build_graph_for_each_target():
    for sid in ("dcinside", "culture_info", "product_hunt", "gdelt"):
        g = build_strategy_graph(capability_for(sid))
        assert g.source_id == sid and len(g.nodes) >= 3
        assert g.node("evidence_gate") is not None        # 모든 그래프는 evidence_gate로 종결


def test_dcinside_detail_has_preview_fallback():
    g = build_strategy_graph(capability_for("dcinside"))
    # HIGH 민감 source의 detail 본문 노드는 preview-only fallback을 반드시 가진다(보수성).
    assert "detail_body_selector_extract" in g.fallback_edges
    assert "community_signal_list_preview" in g.fallback_edges["detail_body_selector_extract"]


def test_unsafe_strategies_rejected():
    assert is_unsafe_strategy("proxy_rotation")
    assert is_unsafe_strategy("captcha_solver")
    assert is_unsafe_strategy("robots_ignore")
    safe, rejected = reject_unsafe(["robots_allowed_list_fetch", "proxy_rotation", "captcha_solver"])
    assert safe == ("robots_allowed_list_fetch",)
    assert set(rejected) == {"proxy_rotation", "captcha_solver"}


def test_no_graph_node_is_unsafe():
    for sid in ("dcinside", "culture_info", "product_hunt", "gdelt"):
        g = build_strategy_graph(capability_for(sid))
        for n in g.nodes:
            assert n.name not in UNSAFE_STRATEGIES


def test_build_unknown_source_raises():
    from ingestion.orchestration.source_capability import SourceCapability
    bogus = SourceCapability("bogus", "x", "y", True, False, False, False, True, False,
                             False, None, "low")
    with pytest.raises(ValueError):
        build_strategy_graph(bogus)
