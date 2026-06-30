"""ADR#93 §14·§20 — community_feedback_loop_contract 테스트(11단계 LOOP 순서·runtime 0·응답 생성 0·날조 0).

community_interaction_future_gate(11요구 flat checklist)를 COMPOSE 하는 LOOP SEQUENCE 계약 —
각 단계의 선행 요구는 그 gate 가 단일 출처(재선언 0). 본 테스트는 §20 #49-#56 을 검증한다."""
from __future__ import annotations

from backend.app.tools.community_feedback_loop_contract import (
    CFL_DEFINED_RUNTIME_DISABLED,
    LOOP_STEP_ORDER,
    build_community_feedback_loop_contract,
    sanitized_community_feedback_loop_contract,
)
from backend.app.tools.community_interaction_future_gate import COMMUNITY_GATE_REQUIREMENTS

_EXPECTED_ORDER = (
    "user_comment_received",
    "comment_classification",
    "safety_moderation",
    "question_or_reaction_detection",
    "source_followup_needed",
    "agent_followup_collection",
    "post_update_candidate",
    "human_or_policy_review",
    "reply_candidate",
    "reply_publish_gate",
    "audit_log",
)
_REQUIRED_STEP_FIELDS = ("step", "description", "requires", "forbidden_now", "runtime_status")


def _step(out: dict, name: str) -> dict:
    return next(s for s in out["loop_steps"] if s["step"] == name)


# ── §20-49: loop steps defined(== LOOP_STEP_ORDER·11단계·각 5필드) ────────────────────────────────────────────
def test_49_loop_steps_defined():
    out = build_community_feedback_loop_contract()
    assert tuple(out["loop_step_order"]) == _EXPECTED_ORDER == LOOP_STEP_ORDER
    assert out["loop_step_count"] == 11
    assert len(out["loop_steps"]) == 11
    for s in out["loop_steps"]:
        for f in _REQUIRED_STEP_FIELDS:
            assert f in s, (s.get("step"), f)


# ── §20-50: moderation required ──────────────────────────────────────────────────────────────────────────────
def test_50_moderation_required():
    assert build_community_feedback_loop_contract()["moderation_required"] is True


# ── §20-51: privacy gate required ────────────────────────────────────────────────────────────────────────────
def test_51_privacy_gate_required():
    assert build_community_feedback_loop_contract()["privacy_gate_required"] is True


# ── §20-52: audit log required ───────────────────────────────────────────────────────────────────────────────
def test_52_audit_log_required():
    assert build_community_feedback_loop_contract()["audit_log_required"] is True


# ── §20-53: source citation required ─────────────────────────────────────────────────────────────────────────
def test_53_source_citation_required():
    assert build_community_feedback_loop_contract()["source_citation_required"] is True


# ── §20-54: uncertainty required ─────────────────────────────────────────────────────────────────────────────
def test_54_uncertainty_required():
    assert build_community_feedback_loop_contract()["uncertainty_required"] is True


# ── §20-55: no reply generated(응답 생성 0·auto-reply 0·runtime 0) ───────────────────────────────────────────
def test_55_no_reply_generated():
    out = build_community_feedback_loop_contract()
    assert out["reply_generated"] is False
    assert out["comment_auto_reply_enabled"] is False
    assert out["runtime_enabled"] is False


# ── §20-56: agent follow-up cannot fabricate facts ──────────────────────────────────────────────────────────
def test_56_agent_followup_no_fabrication():
    out = build_community_feedback_loop_contract()
    assert out["agent_followup_can_fabricate_facts"] is False
    s = _step(out, "agent_followup_collection")
    assert any("날조" in fa for fa in s["forbidden_now"])


# ── COMPOSE: community_interaction_future_gate 참조(11요구 재선언 0) ──────────────────────────────────────────
def test_references_community_interaction_gate():
    out = build_community_feedback_loop_contract()
    assert out["references_community_interaction_gate"] is True
    assert out["community_gate_requirements_count"] == len(COMMUNITY_GATE_REQUIREMENTS)
    assert "community_interaction_gate_status" in out


# ── 각 step.requires 는 COMMUNITY_GATE_REQUIREMENTS 만 참조(단일 출처) ────────────────────────────────────────
def test_requires_reference_gate_requirements():
    out = build_community_feedback_loop_contract()
    req_set = set(COMMUNITY_GATE_REQUIREMENTS)
    for s in out["loop_steps"]:
        for r in s["requires"]:
            assert r in req_set, (s["step"], r)


# ── status/runtime 불변(top-level) ──────────────────────────────────────────────────────────────────────────
def test_status_and_runtime_invariants():
    out = build_community_feedback_loop_contract()
    assert out["community_feedback_loop_status"] == CFL_DEFINED_RUNTIME_DISABLED
    assert out["operation_name"] == "community_feedback_loop_contract"
    assert out["contract_version"] == "community_feedback_loop_v1"
    assert out["user_comment_runtime_open"] is False
    assert out["community_is_evidence_anchor"] is False
    assert out["merge_allowed"] is False
    assert out["public_iu_allowed"] is False
    assert out["llm_invoked"] is False
    assert out["same_event_asserted"] is False
    assert out["r2_r7_no_go"] is True


# ── sanitized 투영(aggregate-only·loop step 본문 제외) ───────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_community_feedback_loop_contract()
    s = sanitized_community_feedback_loop_contract(out)
    assert "loop_steps" not in s
    assert s["community_feedback_loop_status"] == CFL_DEFINED_RUNTIME_DISABLED
    assert s["loop_step_count"] == 11
    assert s["runtime_enabled"] is False
    assert s["reply_generated"] is False
