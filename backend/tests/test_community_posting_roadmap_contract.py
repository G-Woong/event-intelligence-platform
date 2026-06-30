"""ADR#91 §14 — community_posting_roadmap_contract 테스트(8단계 순서·publish/comment runtime 0·reaction_to only·날조 0).

기존 community_interaction_future_gate(11요구 flat)와 DISTINCT한 ordered roadmap. terminal 단계가 그 gate 를 참조."""
from __future__ import annotations

from backend.app.tools.community_posting_roadmap_contract import (
    ROADMAP_DEFINED_RUNTIME_DISABLED,
    STAGE_ORDER,
    build_community_posting_roadmap_contract,
    sanitized_community_posting_roadmap,
)

_EXPECTED_ORDER = (
    "stage_0_internal_evidence_pipeline",
    "stage_1_reviewer_gold_and_merge_gate",
    "stage_2_hot_intelligence_post_draft_contract",
    "stage_3_public_readiness_gate",
    "stage_4_community_reaction_attachment",
    "stage_5_moderation_and_safety_gate",
    "stage_6_comment_reply_gate",
    "stage_7_agent_followup_collection",
)
_REQUIRED_STAGE_FIELDS = ("entry_conditions", "allowed_actions", "forbidden_actions", "evidence_requirements",
                          "human_label_requirements", "runtime_status", "next_gate")


def _stage(out: dict, name: str) -> dict:
    return next(s for s in out["roadmap_stages"] if s["stage"] == name)


# ── §19-65: stages ordered(8단계·next_gate 체인·각 단계 7필드) ───────────────────────────────────────────────
def test_65_stages_ordered():
    out = build_community_posting_roadmap_contract()
    assert tuple(out["stage_order"]) == _EXPECTED_ORDER == STAGE_ORDER
    assert out["stage_count"] == 8
    stages = out["roadmap_stages"]
    for i, s in enumerate(stages):
        for f in _REQUIRED_STAGE_FIELDS:
            assert f in s, (s["stage"], f)
        expected_next = _EXPECTED_ORDER[i + 1] if i + 1 < len(_EXPECTED_ORDER) else ""
        assert s["next_gate"] == expected_next


# ── §19-66: stage before public readiness cannot publish ─────────────────────────────────────────────────────
def test_66_no_publish_before_public_readiness():
    out = build_community_posting_roadmap_contract()
    pr_idx = _EXPECTED_ORDER.index("stage_3_public_readiness_gate")
    for s in out["roadmap_stages"]:
        assert s["publish_runtime"] == "disabled"   # 전 단계 publish runtime 0.
    for s in out["roadmap_stages"][:pr_idx]:
        assert any("publish" in fa for fa in s["forbidden_actions"]), s["stage"]
    assert out["publish_requires_r1_r2"] is True


# ── §19-67: stage before moderation cannot reply ─────────────────────────────────────────────────────────────
def test_67_no_reply_before_moderation():
    out = build_community_posting_roadmap_contract()
    for s in out["roadmap_stages"]:
        assert s["comment_reply_runtime"] == "disabled"   # 전 단계 comment reply runtime 0.
    mod_idx = _EXPECTED_ORDER.index("stage_5_moderation_and_safety_gate")
    reply_idx = _EXPECTED_ORDER.index("stage_6_comment_reply_gate")
    assert mod_idx < reply_idx   # moderation 이 comment reply gate 보다 먼저.
    assert any("comment reply before moderation" in fa
               for fa in _stage(out, "stage_5_moderation_and_safety_gate")["forbidden_actions"])


# ── §19-68: community reaction remains reaction_to only ──────────────────────────────────────────────────────
def test_68_community_reaction_reaction_to_only():
    out = build_community_posting_roadmap_contract()
    assert out["community_reaction_anchor"] is False
    s4 = _stage(out, "stage_4_community_reaction_attachment")
    assert any("reaction_to" in a for a in s4["allowed_actions"])
    assert any("evidence anchor" in fa for fa in s4["forbidden_actions"])


# ── §19-69: agent follow-up cannot fabricate facts ──────────────────────────────────────────────────────────
def test_69_agent_followup_no_fabrication():
    out = build_community_posting_roadmap_contract()
    assert out["agent_followup_fabricates_facts"] is False
    s7 = _stage(out, "stage_7_agent_followup_collection")
    assert any("fabricate facts" in fa for fa in s7["forbidden_actions"])
    assert any("rate limit" in ec for ec in s7["entry_conditions"])


# ── §19-70/71/72: privacy·moderation·audit gate 필수 ─────────────────────────────────────────────────────────
def test_70_71_72_privacy_moderation_audit_required():
    out = build_community_posting_roadmap_contract()
    assert out["privacy_user_data_gate_required"] is True
    assert out["moderation_gate_required"] is True
    assert out["audit_log_required"] is True
    s5 = _stage(out, "stage_5_moderation_and_safety_gate")
    assert any("privacy_user_data_policy" in e for e in s5["evidence_requirements"])
    s6 = _stage(out, "stage_6_comment_reply_gate")
    assert any("audit log" in h for h in s6["human_label_requirements"])


# ── terminal 단계가 community_interaction_future_gate 참조(11요구 재나열 0) ────────────────────────────────────
def test_references_community_interaction_gate():
    out = build_community_posting_roadmap_contract()
    assert out["references_community_interaction_gate"] is True
    assert "community_interaction_gate_status" in out
    s6 = _stage(out, "stage_6_comment_reply_gate")
    assert any("community_interaction_future_gate.all_requirements_met" in ec for ec in s6["entry_conditions"])


# ── runtime No-Go(전 단계·top-level) ─────────────────────────────────────────────────────────────────────────
def test_runtime_disabled():
    out = build_community_posting_roadmap_contract()
    assert out["community_posting_roadmap_status"] == ROADMAP_DEFINED_RUNTIME_DISABLED
    assert out["runtime_enabled"] is False
    assert out["comment_reply_generation"] is False
    assert out["public_post_runtime_enabled"] is False


# ── sanitized 투영 ────────────────────────────────────────────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_community_posting_roadmap_contract()
    s = sanitized_community_posting_roadmap(out)
    assert set(s) == {"community_posting_roadmap_status", "stage_count", "runtime_enabled",
                      "comment_reply_generation", "publish_requires_r1_r2"}
