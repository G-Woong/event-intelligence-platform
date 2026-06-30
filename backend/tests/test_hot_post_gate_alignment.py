"""ADR#91 §13 — hot_post_gate_alignment 테스트(public_readiness 를 gold/merge/evidence/source-role/community 에 결속).

모든 요구 충족이어도 runtime_enabled=False(public post runtime No-Go). hotness/community/official 단독 게시 0."""
from __future__ import annotations

from backend.app.tools.hot_post_gate_alignment import (
    GATE_REQUIREMENTS_MET_RUNTIME_DISABLED,
    GATE_REQUIREMENTS_UNMET,
    build_hot_post_gate_alignment,
    sanitized_hot_post_gate_alignment,
)


def _full_draft(**over) -> dict:
    """11개 요구를 모두 충족하는 draft(테스트가 한 요구만 깬다)."""
    d = {
        "verified_event_identity": True,
        "production_gold_count": 200,
        "merge_gate_status": "passed",
        "official_evidence": [{"source": "federal_register"}],
        "news_corroboration": [{"source": "guardian"}],
        "anchor_role": "official",
        "uncertainty_summary": "residual uncertainty noted",
        "human_label_status": "gold",
        "public_safety_review": True,
        "moderation_policy_ready": True,
        "reply_policy_ready": True,
    }
    d.update(over)
    return d


# ── 전 요구 충족 → public_readiness True · 단 runtime 은 여전히 disabled ────────────────────────────────────────
def test_all_requirements_met_but_runtime_disabled():
    out = build_hot_post_gate_alignment(_full_draft())
    assert out["public_readiness"] is True
    assert out["hot_post_gate_status"] == GATE_REQUIREMENTS_MET_RUNTIME_DISABLED
    assert out["missing_requirements"] == []
    # 전 요구 충족이어도 runtime 은 No-Go·게시 0.
    assert out["runtime_enabled"] is False
    assert out["publishable"] is False


# ── §19-56: no production gold → public_readiness false ──────────────────────────────────────────────────────
def test_56_no_production_gold():
    out = build_hot_post_gate_alignment(_full_draft(production_gold_count=0))
    assert out["public_readiness"] is False
    assert "production_gold_available" in out["missing_requirements"]


# ── §19-57: no MERGE_GATE → false ───────────────────────────────────────────────────────────────────────────
def test_57_no_merge_gate():
    out = build_hot_post_gate_alignment(_full_draft(merge_gate_status="pending"))
    assert out["public_readiness"] is False
    assert "merge_gate_passed" in out["missing_requirements"]


# ── §19-58: community-only → false ──────────────────────────────────────────────────────────────────────────
def test_58_community_only():
    out = build_hot_post_gate_alignment({"anchor_role": "community", "community_reaction_layer": [{"r": 1}]})
    assert out["public_readiness"] is False
    assert "source_role_guard_passed" in out["missing_requirements"]
    assert "community_layer_reaction_to_only" in out["missing_requirements"]
    assert out["community_buzz_publishable"] is False


# ── §19-59: hotness-only → false ────────────────────────────────────────────────────────────────────────────
def test_59_hotness_only():
    out = build_hot_post_gate_alignment({"why_it_is_hot": "viral", "hotness_score_hint": "high"})
    assert out["public_readiness"] is False
    assert out["hotness_alone_publishable"] is False
    # 핵심 evidence/gold/merge 요구가 missing.
    assert "production_gold_available" in out["missing_requirements"]
    assert "merge_gate_passed" in out["missing_requirements"]


# ── §19-60: official-only → false(news 교차/gold/merge 부재) ──────────────────────────────────────────────────
def test_60_official_only():
    out = build_hot_post_gate_alignment({"official_evidence": [{"source": "fr"}], "anchor_role": "official"})
    assert out["public_readiness"] is False
    assert out["official_record_alone_publishable"] is False
    assert "news_corroboration_present" in out["missing_requirements"]


# ── §19-61: uncertainty missing → false ─────────────────────────────────────────────────────────────────────
def test_61_uncertainty_missing():
    out = build_hot_post_gate_alignment(_full_draft(uncertainty_summary=""))
    assert out["public_readiness"] is False
    assert "uncertainty_summary_present" in out["missing_requirements"]


# ── §19-62/63/64: runtime/post body/comment reply 항상 False ──────────────────────────────────────────────────
def test_62_63_64_runtime_constants_false():
    for draft in (None, _full_draft()):
        out = build_hot_post_gate_alignment(draft)
        assert out["runtime_enabled"] is False
        assert out["public_post_body_generated"] is False
        assert out["comment_reply_generation"] is False
        assert out["llm_headline_publishable"] is False


# ── 빈 draft → 실질 요구 전부 미충족(community-reaction-only 는 community 레이어 부재라 vacuously met) ────────────
def test_empty_draft_substantive_requirements_missing():
    out = build_hot_post_gate_alignment()
    assert out["public_readiness"] is False
    assert out["hot_post_gate_status"] == GATE_REQUIREMENTS_UNMET
    # community_layer_reaction_to_only 은 community 레이어가 없으면 오용도 없어 vacuously 충족 → 실질 요구 10개가 missing.
    substantive = [r for r in out["requirements"] if r != "community_layer_reaction_to_only"]
    assert set(substantive) <= set(out["missing_requirements"])
    assert "community_layer_reaction_to_only" not in out["missing_requirements"]
    assert out["missing_requirement_count"] == 10


# ── sanitized 투영 ────────────────────────────────────────────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_hot_post_gate_alignment()
    s = sanitized_hot_post_gate_alignment(out)
    assert set(s) == {"hot_post_gate_status", "hot_post_public_readiness", "missing_requirement_count",
                      "runtime_enabled"}
    assert s["hot_post_public_readiness"] is False
