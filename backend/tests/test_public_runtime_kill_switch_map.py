"""ADR#94 — public_runtime_kill_switch_map 테스트(8 public runtime 기본 DISABLED·override 불가·network 0).

모든 공개 runtime(hot post / comment reply / public IU / LLM / embedding / KG / DB write / sending)은 기본
disabled 이며, comment_reply·public_hot_post 의 disabled 는 community_interaction_future_gate /
hot_post_gate_alignment 단일 출처 게이트에서 COMPOSE(재선언 0). operator override 는 R1(gold) AND R2(merge)
AND 명시 ADR AND tests 가 모두 있어야만 가능 — 이번 턴엔 전부 미충족이라 항상 False."""
from __future__ import annotations

from backend.app.tools.public_runtime_kill_switch_map import (
    PRKS_ALL_DISABLED,
    PUBLIC_RUNTIME_DIMENSIONS,
    build_public_runtime_kill_switch_map,
    sanitized_public_runtime_kill_switch_map,
)

_EXPECTED_DIMENSIONS = (
    "public_hot_post_runtime",
    "comment_reply_runtime",
    "public_iu_runtime",
    "llm_generation_runtime",
    "embedding_runtime",
    "kg_runtime",
    "db_write_runtime",
    "actual_sending_runtime",
)


def _dim(out: dict, name: str) -> dict:
    return next(d for d in out["disabled_dimensions"] if d["dimension"] == name)


# ── 8개 public runtime 전부 disabled(iterate·각 disabled True·len==8) ─────────────────────────────────────────
def test_all_eight_runtimes_disabled():
    out = build_public_runtime_kill_switch_map()
    dims = out["disabled_dimensions"]
    assert len(dims) == 8
    assert tuple(d["dimension"] for d in dims) == _EXPECTED_DIMENSIONS == PUBLIC_RUNTIME_DIMENSIONS
    for d in dims:
        assert d["disabled"] is True, d["dimension"]
        assert d["enforced_by"]   # 비어있지 않은 citation
    assert out["all_public_runtime_disabled"] is True


# ── public hot post disabled(hot_post_gate_alignment COMPOSE) ────────────────────────────────────────────────
def test_public_hot_post_disabled():
    out = build_public_runtime_kill_switch_map()
    d = _dim(out, "public_hot_post_runtime")
    assert d["disabled"] is True
    assert "hot_post_gate_alignment" in d["enforced_by"]


# ── comment reply disabled(community_interaction_future_gate COMPOSE) ────────────────────────────────────────
def test_comment_reply_disabled():
    out = build_public_runtime_kill_switch_map()
    d = _dim(out, "comment_reply_runtime")
    assert d["disabled"] is True
    assert "community_interaction_future_gate" in d["enforced_by"]


# ── public IU disabled ───────────────────────────────────────────────────────────────────────────────────────
def test_public_iu_disabled():
    out = build_public_runtime_kill_switch_map()
    assert _dim(out, "public_iu_runtime")["disabled"] is True
    assert out["public_iu_allowed"] is False


# ── LLM runtime disabled(config LLM_PROVIDER='mock' citation) ────────────────────────────────────────────────
def test_llm_runtime_disabled():
    out = build_public_runtime_kill_switch_map()
    d = _dim(out, "llm_generation_runtime")
    assert d["disabled"] is True
    assert "mock" in d["enforced_by"]


# ── embedding runtime disabled(config EMBEDDING_PROVIDER='mock' citation) ────────────────────────────────────
def test_embedding_runtime_disabled():
    out = build_public_runtime_kill_switch_map()
    d = _dim(out, "embedding_runtime")
    assert d["disabled"] is True
    assert "mock" in d["enforced_by"]


# ── DB write runtime disabled ────────────────────────────────────────────────────────────────────────────────
def test_db_write_runtime_disabled():
    out = build_public_runtime_kill_switch_map()
    assert _dim(out, "db_write_runtime")["disabled"] is True


# ── R1 missing blocks override(r1=False, r2=True → operator_override_allowed False) ──────────────────────────
def test_r1_missing_blocks_override():
    out = build_public_runtime_kill_switch_map(r1_satisfied=False, r2_satisfied=True)
    assert out["gate_inputs_satisfied"] is False   # R1 누락이 gate inputs 를 떨어뜨림(demonstrably gate).
    assert out["operator_override_allowed"] is False


# ── R2 missing blocks override(r1=True, r2=False → False) ────────────────────────────────────────────────────
def test_r2_missing_blocks_override():
    out = build_public_runtime_kill_switch_map(r1_satisfied=True, r2_satisfied=False)
    assert out["gate_inputs_satisfied"] is False   # R2 누락이 gate inputs 를 떨어뜨림.
    assert out["operator_override_allowed"] is False


# ── both set still False this turn(명시 ADR+tests 도 필요·override_requires_tests True) ──────────────────────
def test_both_set_still_blocked_this_turn():
    out = build_public_runtime_kill_switch_map(r1_satisfied=True, r2_satisfied=True)
    # R1 AND R2 만족이어도 명시 ADR+tests 가 더 필요 → 여전히 override 불가.
    assert out["gate_inputs_satisfied"] is True
    assert out["explicit_adr_and_tests_present"] is False
    assert out["override_requires_tests"] is True
    assert out["operator_override_allowed"] is False


# ── 이 모듈 자체 불변(무엇도 실행/생성/전송하지 않음) ──────────────────────────────────────────────────────────
def test_public_post_body_not_generated():
    assert build_public_runtime_kill_switch_map()["public_post_body_generated"] is False


def test_comment_reply_not_generated():
    assert build_public_runtime_kill_switch_map()["comment_reply_generated"] is False


def test_no_db_write():
    assert build_public_runtime_kill_switch_map()["db_write"] is False


def test_no_llm_invoked():
    assert build_public_runtime_kill_switch_map()["llm_invoked"] is False


def test_no_embedding_invoked():
    assert build_public_runtime_kill_switch_map()["embedding_invoked"] is False


# ── status / 추가 불변(network 0·merge 0·public IU 0·전송 0) ─────────────────────────────────────────────────
def test_status_and_invariants():
    out = build_public_runtime_kill_switch_map()
    assert out["public_runtime_kill_switch_status"] == PRKS_ALL_DISABLED
    assert out["operation_name"] == "public_runtime_kill_switch_map"
    assert out["contract_version"] == "public_runtime_kill_switch_map_v1"
    assert out["network_invoked"] is False
    assert out["merge_allowed"] is False
    assert out["public_iu_allowed"] is False
    assert out["actual_sending_performed"] is False
    assert out["override_requires_explicit_adr"] is True


# ── COMPOSE: 기존 단일-출처 게이트 참조(재선언 0) ─────────────────────────────────────────────────────────────
def test_compose_references_gates():
    out = build_public_runtime_kill_switch_map()
    assert out["references_community_interaction_gate"] is True
    assert out["references_hot_post_gate_alignment"] is True
    assert "community_interaction_gate_status" in out
    assert "hot_post_gate_status" in out


# ── required_gates: R1 + R2 + 명시 ADR + tests(전부 must_pass) ───────────────────────────────────────────────
def test_required_gates_present():
    out = build_public_runtime_kill_switch_map()
    gates = {g["gate"] for g in out["required_gates"]}
    assert {"r1_production_gold", "r2_merge_gate", "explicit_runtime_override_adr", "override_tests"} <= gates
    for g in out["required_gates"]:
        assert g["must_pass"] is True


# ── sanitized 투영(aggregate-only·dimension 본문 제외) ───────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_public_runtime_kill_switch_map()
    s = sanitized_public_runtime_kill_switch_map(out)
    assert "disabled_dimensions" not in s
    assert s["public_runtime_kill_switch_status"] == PRKS_ALL_DISABLED
    assert s["all_public_runtime_disabled"] is True
    assert s["disabled_dimension_count"] == 8
    assert s["operator_override_allowed"] is False
    assert s["override_requires_tests"] is True
