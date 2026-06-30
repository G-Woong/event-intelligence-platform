"""ADR#95 §15/§21 (#49-56) — ai-replies comment/reply runtime gate-design contract 테스트.

검증: 필요한 게이트 10개 전부 열거(정확한 이름)·runtime_enabled False·reply_generation_enabled False·LLM 0·
default(satisfied None)=차단 게이트 전부 미충족→BLOCKED·차단 게이트 개별 미충족→BLOCKED·차단 4개 전부 충족→READY·
current_endpoint_status="ungated_mock_endpoint"(실제 라우트 사실)·endpoint 미수정·PII-safe·sanitized 에 status 포함.
"""
from __future__ import annotations

from backend.app.tools.ai_replies_gate_design import (
    BLOCKING_GATES,
    GATE_DESIGN_BLOCKED,
    GATE_DESIGN_READY,
    build_ai_replies_gate_design,
    sanitized_ai_replies_gate_design,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

_EXPECTED_GATES = [
    "public_readiness_gate",
    "moderation_gate",
    "privacy_gate",
    "audit_log_gate",
    "source_citation_gate",
    "uncertainty_policy_gate",
    "rate_limit_gate",
    "human_override_gate",
    "llm_provider_gate",
    "prompt_safety_gate",
]


def _all_blocking_satisfied() -> dict:
    return {g: True for g in BLOCKING_GATES}


# ── 필요한 게이트 10개 전부 열거(정확한 이름·must_pass) ──
def test_all_ten_required_gates_listed():
    out = build_ai_replies_gate_design()
    assert out["required_gate_count"] == 10
    assert len(out["required_gates"]) == 10
    names = [g["gate"] for g in out["required_gates"]]
    assert names == _EXPECTED_GATES
    assert all(g["must_pass"] is True for g in out["required_gates"])


# ── runtime_enabled 고정 False ──
def test_runtime_disabled():
    assert build_ai_replies_gate_design()["runtime_enabled"] is False


# ── reply 생성 비활성 ──
def test_reply_generation_disabled():
    assert build_ai_replies_gate_design()["reply_generation_enabled"] is False


# ── LLM 호출 0 ──
def test_no_llm_invoked():
    out = build_ai_replies_gate_design()
    assert out["llm_invoked"] is False
    assert out["prompt_executed"] is False
    assert out["network_invoked"] is False


# ── default(satisfied None) → 차단 게이트 전부 미충족 → BLOCKED ──
def test_default_blocks_all_blocking_unmet():
    out = build_ai_replies_gate_design()
    assert out["ai_replies_gate_design_status"] == GATE_DESIGN_BLOCKED
    assert set(out["unmet_blocking_gates"]) == set(BLOCKING_GATES)


# ── 차단 게이트 개별 미충족(나머지 3개 True) → BLOCKED ──
def test_missing_public_readiness_blocks():
    sat = _all_blocking_satisfied()
    del sat["public_readiness_gate"]
    out = build_ai_replies_gate_design(satisfied=sat)
    assert out["ai_replies_gate_design_status"] == GATE_DESIGN_BLOCKED
    assert out["unmet_blocking_gates"] == ["public_readiness_gate"]


def test_missing_moderation_blocks():
    sat = _all_blocking_satisfied()
    del sat["moderation_gate"]
    out = build_ai_replies_gate_design(satisfied=sat)
    assert out["ai_replies_gate_design_status"] == GATE_DESIGN_BLOCKED
    assert out["unmet_blocking_gates"] == ["moderation_gate"]


def test_missing_privacy_blocks():
    sat = _all_blocking_satisfied()
    del sat["privacy_gate"]
    out = build_ai_replies_gate_design(satisfied=sat)
    assert out["ai_replies_gate_design_status"] == GATE_DESIGN_BLOCKED
    assert out["unmet_blocking_gates"] == ["privacy_gate"]


def test_missing_audit_log_blocks():
    sat = _all_blocking_satisfied()
    del sat["audit_log_gate"]
    out = build_ai_replies_gate_design(satisfied=sat)
    assert out["ai_replies_gate_design_status"] == GATE_DESIGN_BLOCKED
    assert out["unmet_blocking_gates"] == ["audit_log_gate"]


# ── 차단 4개 전부 충족 → READY(그래도 runtime_disabled) ──
def test_all_blocking_satisfied_ready():
    out = build_ai_replies_gate_design(satisfied=_all_blocking_satisfied())
    assert out["ai_replies_gate_design_status"] == GATE_DESIGN_READY
    assert out["unmet_blocking_gates"] == []
    assert out["runtime_enabled"] is False  # READY 여도 runtime 0.


# ── current_endpoint_status = 실제 라우트 사실(ungated mock) ──
def test_current_endpoint_status_ungated_mock():
    assert build_ai_replies_gate_design()["current_endpoint_status"] == "ungated_mock_endpoint"


# ── endpoint 미수정 ──
def test_endpoint_not_modified():
    out = build_ai_replies_gate_design()
    assert out["endpoint_modified"] is False
    assert out["public_post_body_generated"] is False
    assert out["production_gold_count"] == 0


# ── PII-safe 재귀 가드 통과(forbidden 키 0) ──
def test_assert_pii_safe_passes():
    out = build_ai_replies_gate_design(satisfied=_all_blocking_satisfied())
    _assert_pii_safe(out, _path="test_ai_replies_gate_design")  # raise 없으면 통과.


# ── sanitized 투영은 build 출력의 subset 이고 status 포함 ──
def test_sanitized_has_status_and_is_subset():
    out = build_ai_replies_gate_design()
    s = sanitized_ai_replies_gate_design(out)
    assert set(s.keys()) <= set(out.keys())
    assert s["ai_replies_gate_design_status"] == out["ai_replies_gate_design_status"]
