"""ADR#93 §20 #42-#48 — hot_post_activation_map 테스트(공개 runtime 활성화 9단계 순서·runtime 0·R1 AND R2 + operator 승인).

이 모듈은 community_posting_roadmap_contract(제품 LIFECYCLE)와 DISTINCT — 공개 runtime ACTIVATION GATE SEQUENCE 다.
검증: R1/R2 전 public publish 차단 · public readiness 필요 · operator 승인 필요 · community reaction 은 verified
event 후 reaction_to only(anchor 0) · comment reply 는 community gate 전 0 · runtime 기본 disabled.
"""
from __future__ import annotations

from backend.app.tools.community_interaction_future_gate import COMMUNITY_GATE_REQUIREMENTS
from backend.app.tools.hot_intelligence_post_contract import is_valid_anchor_role
from backend.app.tools.hot_post_activation_map import (
    HPA_DEFINED_RUNTIME_DISABLED,
    STAGE_ORDER,
    build_hot_post_activation_map,
    sanitized_hot_post_activation_map,
)
from backend.app.tools.hot_post_gate_alignment import HOT_POST_GATE_REQUIREMENTS
from backend.app.tools.hot_post_preview_guard import (
    HPV_BLOCKED,
    HPV_INTERNAL_ONLY,
    build_hot_post_preview_guard,
)

_EXPECTED_ORDER = (
    "stage_0_internal_preview_blocked",
    "stage_1_r1_gold_available",
    "stage_2_r2_merge_gate_passed",
    "stage_3_hot_post_public_readiness_check",
    "stage_4_internal_preview_allowed",
    "stage_5_public_publish_candidate",
    "stage_6_public_publish_requires_operator_approval",
    "stage_7_community_reaction_attachment",
    "stage_8_comment_reply_gate",
)
_REQUIRED_STAGE_FIELDS = ("entry_conditions", "allowed_actions", "forbidden_actions", "required_evidence",
                          "runtime_status", "next_gate")


def _stage(out: dict, name: str) -> dict:
    return next(s for s in out["activation_stages"] if s["stage"] == name)


def _texts(s: dict) -> list[str]:
    return s["entry_conditions"] + s["allowed_actions"] + s["forbidden_actions"] + s["required_evidence"]


def _valid_internal_draft() -> dict:
    # structural 통과(official evidence anchor·uncertainty·community reaction-only) → HPV_INTERNAL_ONLY(단 public 차단).
    return {
        "anchor_role": "official",
        "official_evidence": {"url": "https://www.federalregister.gov/doc", "source_type": "official"},
        "uncertainty_summary": "single official source; news corroboration pending",
    }


# ── stage order fixed(9단계·next_gate 체인·각 단계 7필드) ──────────────────────────────────────────────────────
def test_stage_order_fixed():
    out = build_hot_post_activation_map()
    assert tuple(out["stage_order"]) == _EXPECTED_ORDER == STAGE_ORDER
    assert out["stage_count"] == 9
    stages = out["activation_stages"]
    assert len(stages) == 9
    for i, s in enumerate(stages):
        assert s["stage"] == _EXPECTED_ORDER[i]
        for f in _REQUIRED_STAGE_FIELDS:
            assert f in s, (s["stage"], f)
        expected_next = _EXPECTED_ORDER[i + 1] if i + 1 < len(_EXPECTED_ORDER) else ""
        assert s["next_gate"] == expected_next


# ── #42: public publish blocked before R1(production_gold_available) — stage_5/6 forbidden/entry references R1 ──
def test_42_public_publish_blocked_before_r1():
    out = build_hot_post_activation_map()
    for name in ("stage_5_public_publish_candidate", "stage_6_public_publish_requires_operator_approval"):
        s = _stage(out, name)
        assert any("production_gold_available" in t for t in _texts(s)), name
        assert any("public post body before R1 production_gold_available" in fa for fa in s["forbidden_actions"]), name
    assert out["public_readiness_requires_r1"] is True
    assert out["publish_requires_r1_r2"] is True


# ── #43: public publish blocked before R2(merge_gate_passed) — references R2 ──────────────────────────────────
def test_43_public_publish_blocked_before_r2():
    out = build_hot_post_activation_map()
    for name in ("stage_5_public_publish_candidate", "stage_6_public_publish_requires_operator_approval"):
        s = _stage(out, name)
        assert any("merge_gate_passed" in t for t in _texts(s)), name
        assert any("R2 merge_gate_passed" in fa for fa in s["forbidden_actions"]), name
    assert out["public_readiness_requires_r2"] is True


# ── #44: public publish requires public readiness — stage_3 present, references HOT_POST_GATE_REQUIREMENTS ──────
def test_44_public_publish_requires_public_readiness():
    out = build_hot_post_activation_map()
    s3 = _stage(out, "stage_3_hot_post_public_readiness_check")
    assert any("HOT_POST_GATE_REQUIREMENTS" in t for t in _texts(s3))
    assert out["references_hot_post_gate_requirements"] is True
    assert out["hot_post_gate_requirements_count"] == len(HOT_POST_GATE_REQUIREMENTS) == 11
    # 현 단계 readiness 미충족(gold/merge 부재) — 게시 불가.
    assert out["hot_post_public_readiness"] is False


# ── #45: operator approval required for the publish candidate — stage_6 ───────────────────────────────────────
def test_45_operator_approval_required():
    out = build_hot_post_activation_map()
    s6 = _stage(out, "stage_6_public_publish_requires_operator_approval")
    assert any("publish without explicit operator approval" in fa for fa in s6["forbidden_actions"])
    assert any("operator approval" in t for t in _texts(s6))


# ── #46: community reaction attachment only after a verified event — stage_7 entry verified; forbids anchor ─────
def test_46_community_reaction_after_verified_event_only():
    out = build_hot_post_activation_map()
    s7 = _stage(out, "stage_7_community_reaction_attachment")
    assert any("verified" in ec for ec in s7["entry_conditions"])
    assert any("evidence anchor" in fa for fa in s7["forbidden_actions"])
    assert any("is_valid_anchor_role" in fa for fa in s7["forbidden_actions"])
    assert any("reaction_to" in a for a in s7["allowed_actions"])
    # community 는 official/news anchor 가 아님(결속 출처).
    assert is_valid_anchor_role("community") is False
    assert out["community_reaction_anchor"] is False


# ── #47: comment reply blocked before the community gate — stage_8 references community gate ───────────────────
def test_47_comment_reply_blocked_before_gate():
    out = build_hot_post_activation_map()
    s8 = _stage(out, "stage_8_comment_reply_gate")
    assert any("community_interaction_future_gate.all_requirements_met" in ec for ec in s8["entry_conditions"])
    assert any("comment reply before the community_interaction_future_gate" in fa for fa in s8["forbidden_actions"])
    assert out["comment_gate_requirements_count"] == len(COMMUNITY_GATE_REQUIREMENTS) == 11
    assert out["comment_gate_all_requirements_met"] is False


# ── #48: runtime disabled by default(모든 runtime_* invariant False·status·각 단계 runtime_disabled) ────────────
def test_48_runtime_disabled_by_default():
    out = build_hot_post_activation_map()
    assert out["hot_post_activation_map_status"] == HPA_DEFINED_RUNTIME_DISABLED
    assert out["runtime_enabled"] is False
    assert out["public_post_runtime_enabled"] is False
    assert out["public_post_body_generated"] is False
    assert out["comment_reply_generated"] is False
    assert out["comment_reply_runtime_open"] is False
    assert out["community_reaction_anchor"] is False
    assert out["hotness_alone_publishable"] is False
    for s in out["activation_stages"]:
        assert "runtime_disabled" in s["runtime_status"], s["stage"]


# ── public_readiness_requires_r1 / _r2 both True(R1·R2 가 HOT_POST_GATE_REQUIREMENTS 멤버) ──────────────────────
def test_public_readiness_requires_r1_and_r2():
    out = build_hot_post_activation_map()
    assert out["public_readiness_requires_r1"] is True
    assert out["public_readiness_requires_r2"] is True
    assert "production_gold_available" in HOT_POST_GATE_REQUIREMENTS
    assert "merge_gate_passed" in HOT_POST_GATE_REQUIREMENTS


# ── stage_0 preview-blocked 는 build_hot_post_preview_guard 로 증명(preview_publishable 0·public 차단) ──────────
def test_stage_0_preview_blocked_grounded_in_preview_guard():
    out = build_hot_post_activation_map()
    assert out["preview_blocked_status"] == HPV_BLOCKED
    guard = build_hot_post_preview_guard()
    assert guard["preview_publishable"] is False
    assert guard["hot_post_preview_public_blocked"] is True
    s0 = _stage(out, "stage_0_internal_preview_blocked")
    assert any("public post body generation" in fa for fa in s0["forbidden_actions"])


# ── stage_4 internal-preview-allowed 는 HPV_INTERNAL_ONLY(public 은 여전히 차단)에 대응 ────────────────────────
def test_stage_4_internal_preview_grounded_in_preview_guard():
    guard = build_hot_post_preview_guard(_valid_internal_draft())
    assert guard["hot_post_preview_status"] == HPV_INTERNAL_ONLY
    assert guard["hot_post_preview_public_blocked"] is True
    out = build_hot_post_activation_map()
    s4 = _stage(out, "stage_4_internal_preview_allowed")
    assert any("internal-only preview" in a for a in s4["allowed_actions"])
    assert any("public publish from the internal preview" in fa for fa in s4["forbidden_actions"])


# ── No-Go 불변(merge/public IU/same_event/LLM) ────────────────────────────────────────────────────────────────
def test_no_go_invariants():
    out = build_hot_post_activation_map()
    assert out["merge_allowed"] is False
    assert out["public_iu_allowed"] is False
    assert out["same_event_asserted"] is False
    assert out["llm_invoked"] is False
    assert out["r2_r7_no_go"] is True


# ── sanitized 투영(aggregate-only) ────────────────────────────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_hot_post_activation_map()
    s = sanitized_hot_post_activation_map(out)
    assert set(s) == {"hot_post_activation_map_status", "stage_count", "runtime_enabled",
                      "comment_reply_generated", "publish_requires_r1_r2"}
    assert s["stage_count"] == 9
    assert s["runtime_enabled"] is False
