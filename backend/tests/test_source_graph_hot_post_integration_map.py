"""ADR#95 §16/§21 — source_graph_hot_post_integration_map 테스트.

CONTRACT-ONLY 매핑: 15 source-graph component → 21 Hot Intelligence Post field. insight 후보는 게시 불가 ·
timeline update 는 merge gate 전 same_event 단정 0 · community/market 는 non-anchor · public_readiness 는 R1/R2 요구 ·
anchor 는 official_evidence/news_corroboration 뿐 · runtime 0(public post body 0)."""
from __future__ import annotations

from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe
from backend.app.tools.source_graph_hot_post_integration_map import (
    MAP_READY,
    build_source_graph_hot_post_integration_map,
    sanitized_source_graph_hot_post_integration_map,
)

# 매핑이 반드시 커버해야 하는 Hot Post field (ADR#95 §21 #57-62).
_REQUIRED_MAPPED_FIELDS = (
    "event_id", "official_evidence", "news_corroboration", "timeline_updates", "entity_context",
    "community_reaction_layer", "market_signal_layer", "uncertainty_summary", "why_it_is_hot",
    "human_label_status", "merge_gate_status", "public_readiness_status",
)
# component 없이 post 만 갖는 7 field.
_EXPECTED_POST_ONLY = (
    "headline", "last_updated_at", "moderation_status", "post_id", "post_status",
    "reply_policy", "short_hook",
)


def _mapping(out: dict, component: str, field: object = "__any__") -> dict:
    """source_graph_component (+ 선택적 hot_post_field) 로 단일 매핑 dict 조회(없으면 KeyError)."""
    for m in out["mappings"]:
        if m["source_graph_component"] == component and (field == "__any__" or m["hot_post_field"] == field):
            return m
    raise KeyError((component, field))


# ── status == MAP_READY ──────────────────────────────────────────────────────────────────────────────────────
def test_status_is_map_ready():
    out = build_source_graph_hot_post_integration_map()
    assert out["source_graph_hot_post_integration_status"] == MAP_READY
    assert out["contract_version"] == "source_graph_hot_post_integration_map_v1"


# ── 필수 Hot Post field 가 모두 매핑됨 + 21 = mapped ∪ post_only (분할) ─────────────────────────────────────────
def test_required_hot_post_fields_mapped():
    out = build_source_graph_hot_post_integration_map()
    for field in _REQUIRED_MAPPED_FIELDS:
        assert field in out["mapped_hot_post_fields"], field
    assert out["hot_post_field_count"] == 21
    assert len(out["hot_post_fields"]) == 21
    # 21 field 는 mapped 14 + post_only 7 로 정확히 분할된다(중복·누락 0).
    assert set(out["mapped_hot_post_fields"]) | set(out["post_only_fields"]) == set(out["hot_post_fields"])
    assert set(out["mapped_hot_post_fields"]) & set(out["post_only_fields"]) == set()
    assert out["post_only_fields"] == list(_EXPECTED_POST_ONLY)


# ── community 는 anchor 아님 ──────────────────────────────────────────────────────────────────────────────────
def test_community_not_anchor():
    out = build_source_graph_hot_post_integration_map()
    assert out["community_is_anchor"] is False
    assert _mapping(out, "community_reaction_layer")["anchor_eligible"] is False


# ── market 는 anchor 아님 ────────────────────────────────────────────────────────────────────────────────────
def test_market_not_anchor():
    out = build_source_graph_hot_post_integration_map()
    assert out["market_is_anchor"] is False
    assert _mapping(out, "market_signal_layer")["anchor_eligible"] is False


# ── insight 후보는 게시 불가 (insight_candidates→why_it_is_hot 는 candidate-only) ──────────────────────────────
def test_insight_candidate_not_publishable():
    out = build_source_graph_hot_post_integration_map()
    assert out["insight_candidate_publishable"] is False
    m = _mapping(out, "insight_candidates", "why_it_is_hot")
    assert m["anchor_eligible"] is False
    assert "candidate-only" in m["note"]


# ── timeline update 는 same_event 단정 0 ─────────────────────────────────────────────────────────────────────
def test_timeline_update_does_not_assert_same_event():
    out = build_source_graph_hot_post_integration_map()
    assert out["timeline_update_asserts_same_event"] is False
    assert out["same_event_asserted"] is False
    assert "same_event" in _mapping(out, "timeline_updates", "timeline_updates")["note"]


# ── public_readiness 는 R1/R2 요구 ───────────────────────────────────────────────────────────────────────────
def test_public_readiness_requires_r1_r2():
    out = build_source_graph_hot_post_integration_map()
    assert out["public_readiness_requires_r1_r2"] is True


# ── runtime / public post body 비활성 ────────────────────────────────────────────────────────────────────────
def test_runtime_and_public_post_body_disabled():
    out = build_source_graph_hot_post_integration_map()
    assert out["public_post_body_generated"] is False
    assert out["runtime_enabled"] is False
    for k in ("merge_allowed", "llm_invoked", "network_invoked"):
        assert out[k] is False
    assert out["production_gold_count"] == 0


# ── anchor component 는 official_evidence/news_corroboration 뿐 ───────────────────────────────────────────────
def test_anchor_components_official_news_only():
    out = build_source_graph_hot_post_integration_map()
    assert out["anchor_components"] == ["news_corroboration", "official_evidence"]
    assert set(out["non_anchor_components"]).isdisjoint(out["anchor_components"])
    assert len(out["non_anchor_components"]) == 13
    # 매핑 안에서 anchor_eligible True 인 component 도 정확히 그 둘뿐.
    anchor_in_mappings = {m["source_graph_component"] for m in out["mappings"] if m["anchor_eligible"]}
    assert anchor_in_mappings == {"official_evidence", "news_corroboration"}


# ── mapping_count == len(mappings) + 매핑 shape ──────────────────────────────────────────────────────────────
def test_mapping_count_matches_len():
    out = build_source_graph_hot_post_integration_map()
    assert out["mapping_count"] == len(out["mappings"])
    assert out["mapping_count"] == 16
    for m in out["mappings"]:
        assert set(m) == {"source_graph_component", "hot_post_field", "anchor_eligible", "note"}


# ── _assert_pii_safe 통과(forbidden key 0) ───────────────────────────────────────────────────────────────────
def test_pii_safe_passes():
    out = build_source_graph_hot_post_integration_map()
    _assert_pii_safe(out, _path="test_source_graph_hot_post_integration_output")


# ── sanitized 투영에 status 존재 + out 의 subset ─────────────────────────────────────────────────────────────
def test_sanitized_has_status():
    out = build_source_graph_hot_post_integration_map()
    s = sanitized_source_graph_hot_post_integration_map(out)
    assert s["source_graph_hot_post_integration_status"] == MAP_READY
    assert set(s) <= set(out)
    for k in s:
        assert s[k] == out[k]
