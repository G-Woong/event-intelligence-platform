"""ADR#90 §20(44~52) — Hot Intelligence Post contract 테스트(contract 존재·public_readiness false·anchor/truth 금지·runtime 0)."""
from __future__ import annotations

from backend.app.tools.hot_intelligence_post_contract import (
    HOT_POST_FIELDS,
    build_hot_intelligence_post_contract,
    evaluate_hot_post_readiness,
    is_valid_anchor_role,
)


# ── 44. contract exists ────────────────────────────────────────────────────────────────────────────────────
def test_44_contract_exists():
    c = build_hot_intelligence_post_contract()
    assert c["contract_version"] == "hot_intelligence_post_v1"
    assert c["field_count"] == len(HOT_POST_FIELDS) >= 18
    for f in ("headline", "why_it_is_hot", "official_evidence", "news_corroboration",
              "community_reaction_layer", "uncertainty_summary", "public_readiness_status", "reply_policy"):
        assert f in c["fields"]


# ── 45. public_readiness false before R1/R2 ────────────────────────────────────────────────────────────────
def test_45_public_readiness_false_before_gates():
    c = build_hot_intelligence_post_contract()
    assert c["public_readiness_default"] is False
    assert c["runtime_enabled"] is False
    # 완벽해 보이는 draft 라도 runtime disabled → publishable False.
    good_draft = {
        "merge_gate_status": "passed", "official_evidence": ["fr_doc"], "human_label_status": "gold",
        "uncertainty_summary": "moderate",
    }
    r = evaluate_hot_post_readiness(good_draft)
    assert r["publishable"] is False
    assert r["public_readiness_status"] is False


# ── 46. community layer cannot be anchor ───────────────────────────────────────────────────────────────────
def test_46_community_cannot_be_anchor():
    assert is_valid_anchor_role("community") is False
    c = build_hot_intelligence_post_contract()
    assert c["community_is_anchor"] is False
    assert c["non_anchor_roles"]["community"] == "reaction_to"
    r = evaluate_hot_post_readiness({"community_reaction_layer": ["buzz"], "anchor_role": "community"})
    assert "community_reaction_used_as_anchor" in r["violations"]
    assert "non_anchor_role_used_as_anchor:community" in r["violations"]


# ── 47. market signal cannot be anchor ─────────────────────────────────────────────────────────────────────
def test_47_market_cannot_be_anchor():
    assert is_valid_anchor_role("market") is False
    c = build_hot_intelligence_post_contract()
    assert c["market_is_anchor"] is False
    assert c["non_anchor_roles"]["market"] == "signal"
    r = evaluate_hot_post_readiness({"market_signal_layer": ["price"], "anchor_role": "market"})
    assert "market_signal_used_as_anchor" in r["violations"]


# ── 48. search URL candidate cannot be truth ───────────────────────────────────────────────────────────────
def test_48_search_url_not_truth():
    c = build_hot_intelligence_post_contract()
    assert c["search_url_is_truth"] is False
    r = evaluate_hot_post_readiness({"search_url_as_truth": True})
    assert "search_url_candidate_is_not_truth" in r["violations"]


# ── 49. uncertainty required ───────────────────────────────────────────────────────────────────────────────
def test_49_uncertainty_required():
    c = build_hot_intelligence_post_contract()
    assert c["uncertainty_required"] is True
    r = evaluate_hot_post_readiness({"merge_gate_status": "passed", "official_evidence": ["x"],
                                     "human_label_status": "gold"})  # uncertainty 누락.
    assert "uncertainty_must_be_visible" in r["violations"]


# ── 50. human label status required ────────────────────────────────────────────────────────────────────────
def test_50_human_label_required():
    c = build_hot_intelligence_post_contract()
    assert c["human_label_provenance_required"] is True
    r = evaluate_hot_post_readiness({"merge_gate_status": "passed", "official_evidence": ["x"],
                                     "uncertainty_summary": "low"})  # human_label_status 누락.
    assert "human_label_provenance_required" in r["violations"]


# ── 51. reply policy disabled before community runtime gate ────────────────────────────────────────────────
def test_51_reply_policy_disabled():
    c = build_hot_intelligence_post_contract()
    assert c["reply_policy_default"] == "disabled"
    assert c["comment_auto_reply_enabled"] is False
    r = evaluate_hot_post_readiness({})
    assert r["reply_policy"] == "disabled"


# ── 52. no public post body generated ──────────────────────────────────────────────────────────────────────
def test_52_no_public_post_body():
    c = build_hot_intelligence_post_contract()
    assert c["public_post_body_generated"] is False
    assert c["llm_headline_generated"] is False
    r = evaluate_hot_post_readiness({"merge_gate_status": "passed", "official_evidence": ["x"],
                                     "human_label_status": "gold", "uncertainty_summary": "low"})
    assert r["public_post_body_generated"] is False
    assert r["publishable"] is False


# ── no official evidence → no authoritative claim ──────────────────────────────────────────────────────────
def test_no_official_evidence_blocks():
    r = evaluate_hot_post_readiness({"merge_gate_status": "passed", "human_label_status": "gold",
                                     "uncertainty_summary": "low"})  # official_evidence 누락.
    assert "no_official_evidence_no_authoritative_claim" in r["violations"]


# ── before MERGE_GATE → blocked ────────────────────────────────────────────────────────────────────────────
def test_pre_merge_gate_blocks():
    r = evaluate_hot_post_readiness({"official_evidence": ["x"], "human_label_status": "gold",
                                     "uncertainty_summary": "low"})  # merge_gate_status != passed.
    assert "no_public_post_before_merge_gate" in r["violations"]


# ── official/news 는 valid anchor ──────────────────────────────────────────────────────────────────────────
def test_official_news_valid_anchor():
    assert is_valid_anchor_role("official") is True
    assert is_valid_anchor_role("news") is True
    assert is_valid_anchor_role(None) is False
