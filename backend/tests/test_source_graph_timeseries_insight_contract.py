"""ADR#94 — source_graph_timeseries_insight_contract 테스트.

CANDIDATE-ONLY 계약: graph edge 는 MERGE_GATE 전 truth 아님 · community/market/catalog anchor 금지 · insight 게시 0 ·
timeline update 가 same_event 단정 0 · public_readiness 는 R1/R2 요구 · official/news 만 anchor · runtime 0."""
from __future__ import annotations

from backend.app.tools.hot_intelligence_post_contract import is_valid_anchor_role
from backend.app.tools.source_graph_timeseries_insight_contract import (
    build_source_graph_timeseries_insight_contract,
    sanitized_source_graph_timeseries_insight_contract,
)


def _component(out: dict, name: str) -> dict:
    """component 이름으로 단일 component dict 조회(없으면 KeyError)."""
    for c in out["components"]:
        if c["component"] == name:
            return c
    raise KeyError(name)


# ── contract exists / component_count == 15 ────────────────────────────────────────────────────────────────
def test_contract_exists_15_components():
    out = build_source_graph_timeseries_insight_contract()
    assert out["contract_version"] == "source_graph_timeseries_insight_v1"
    assert out["component_count"] == 15
    assert len(out["components"]) == 15
    # 모든 component 가 계약 형태(키 5개)를 갖춘다.
    for c in out["components"]:
        assert set(c) == {"component", "role_or_storage_class", "candidate_until_merge_gate",
                          "anchor_eligible", "citation"}
    assert out["rule_count"] == 9


# ── community cannot be anchor ─────────────────────────────────────────────────────────────────────────────
def test_community_cannot_be_anchor():
    out = build_source_graph_timeseries_insight_contract()
    assert _component(out, "community_reaction_layer")["anchor_eligible"] is False
    assert out["community_is_evidence_anchor"] is False


# ── market cannot be anchor ────────────────────────────────────────────────────────────────────────────────
def test_market_cannot_be_anchor():
    out = build_source_graph_timeseries_insight_contract()
    assert _component(out, "market_signal_layer")["anchor_eligible"] is False
    assert out["market_is_evidence_anchor"] is False


# ── catalog cannot be anchor ───────────────────────────────────────────────────────────────────────────────
def test_catalog_cannot_be_anchor():
    out = build_source_graph_timeseries_insight_contract()
    assert _component(out, "catalog_context_layer")["anchor_eligible"] is False
    assert out["catalog_is_evidence_anchor"] is False


# ── graph edge not truth before MERGE_GATE ─────────────────────────────────────────────────────────────────
def test_graph_edge_candidate_until_merge_gate():
    out = build_source_graph_timeseries_insight_contract()
    assert out["graph_edge_candidate_until_merge_gate"] is True
    assert _component(out, "evidence_edges")["candidate_until_merge_gate"] is True


# ── insight candidate cannot publish ───────────────────────────────────────────────────────────────────────
def test_insight_candidate_not_publishable():
    out = build_source_graph_timeseries_insight_contract()
    assert out["insight_candidate_publishable"] is False
    assert _component(out, "insight_candidates")["anchor_eligible"] is False


# ── timeline update requires evidence / does not assert same_event ─────────────────────────────────────────
def test_timeseries_update_does_not_assert_same_event():
    out = build_source_graph_timeseries_insight_contract()
    assert out["timeseries_update_asserts_same_event"] is False
    assert out["same_event_asserted"] is False
    assert _component(out, "timeline_updates")["candidate_until_merge_gate"] is True


# ── public readiness false before R1/R2 ────────────────────────────────────────────────────────────────────
def test_public_readiness_requires_r1_r2():
    out = build_source_graph_timeseries_insight_contract()
    assert out["public_readiness_requires_r1_r2"] is True
    assert out["public_iu_allowed"] is False


# ── only official/news are anchors ─────────────────────────────────────────────────────────────────────────
def test_only_official_news_are_anchors():
    assert is_valid_anchor_role("official") and is_valid_anchor_role("news")
    assert not is_valid_anchor_role("community")
    out = build_source_graph_timeseries_insight_contract()
    assert out["official_news_only_anchor"] is True
    anchor_components = {c["component"] for c in out["components"] if c["anchor_eligible"]}
    assert anchor_components == {"official_evidence", "news_corroboration"}


# ── runtime/No-Go 불변(항상 False·r2_r7_no_go True) ──────────────────────────────────────────────────────────
def test_runtime_nogo_invariants():
    out = build_source_graph_timeseries_insight_contract()
    for k in ("runtime_enabled", "merge_allowed", "same_event_asserted", "llm_invoked",
              "embedding_invoked", "public_iu_allowed", "network_invoked", "llm_summary_enabled"):
        assert out[k] is False
    assert out["r2_r7_no_go"] is True


# ── sanitized 투영 subset ──────────────────────────────────────────────────────────────────────────────────
def test_sanitized_projection_subset():
    out = build_source_graph_timeseries_insight_contract()
    s = sanitized_source_graph_timeseries_insight_contract(out)
    assert set(s) == {"source_graph_timeseries_contract_status", "component_count",
                      "runtime_enabled", "public_iu_allowed", "r2_r7_no_go"}
    assert set(s) <= set(out)
    for k in s:
        assert s[k] == out[k]
    assert s["component_count"] == 15
