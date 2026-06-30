"""ADR#90 — operator_payload_authoring_helper 테스트(템플릿 only·operator_confirmed/live_approved=false·live 트리거 0)."""
from __future__ import annotations

from backend.app.tools.operator_payload_authoring_helper import (
    DRAFT_DIR,
    build_operator_payload_authoring,
    draft_template_path,
    emit_missing_fields_checklist,
    generate_operator_fillable_payload_template,
    validate_template_not_real_payload,
)
from backend.app.tools.operator_regulatory_event_intake import run_operator_regulatory_event_intake
from backend.app.tools.operator_regulatory_event_payload import REAL_PAYLOAD_PATH
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank


def _selected_seed() -> dict:
    bank = build_regulatory_event_seed_bank()
    seed = bank["selected_seed_for_next_live_run"]
    assert isinstance(seed, dict)
    return seed


# ── 17. authoring helper emits template only ───────────────────────────────────────────────────────────────
def test_17_authoring_helper_emits_template_only():
    out = build_operator_payload_authoring()
    assert out["authoring_status"] == "operator_payload_template_ready"
    assert out["payload_template_ready"] is True
    assert isinstance(out["payload_template"], dict)
    # 코드가 confirmed event 를 fabricate 하지 않는다.
    assert out["code_fabricated_confirmed_event"] is False


# ── 18. template has operator_confirmed=false ──────────────────────────────────────────────────────────────
def test_18_template_operator_confirmed_false():
    seed = _selected_seed()
    t = generate_operator_fillable_payload_template(seed)
    assert t["operator_confirmed"] is False
    assert build_operator_payload_authoring()["operator_confirmed"] is False


# ── 19. template has live_approved=false ───────────────────────────────────────────────────────────────────
def test_19_template_live_approved_false():
    seed = _selected_seed()
    t = generate_operator_fillable_payload_template(seed)
    assert t["live_approved"] is False
    assert build_operator_payload_authoring()["live_approved"] is False


# ── 20. template path != real payload path ─────────────────────────────────────────────────────────────────
def test_20_template_path_not_real_payload_path():
    out = build_operator_payload_authoring()
    assert out["template_path"] != REAL_PAYLOAD_PATH
    assert out["template_path_equals_real_payload_path"] is False
    assert out["template_path"].startswith(DRAFT_DIR)
    assert draft_template_path("x") != REAL_PAYLOAD_PATH


# ── 21. missing fields checklist generated ─────────────────────────────────────────────────────────────────
def test_21_missing_fields_checklist_generated():
    out = build_operator_payload_authoring()
    assert isinstance(out["missing_fields"], list)
    assert out["missing_field_count"] >= 1
    joined = " ".join(out["missing_fields"]).lower()
    assert "operator_confirmed" in joined
    assert "live_approved" in joined


# ── 22. next_action is actionable ──────────────────────────────────────────────────────────────────────────
def test_22_next_action_is_actionable():
    out = build_operator_payload_authoring()
    na = out["next_action"].lower()
    assert na
    assert REAL_PAYLOAD_PATH in out["next_action"]   # operator 가 어디에 저장할지 명시.
    assert "operator_confirmed" in na and "live_approved" in na


# ── 23. helper never invokes network (pure·deterministic·disk write 0) ─────────────────────────────────────
def test_23_helper_deterministic_no_network():
    # 같은 입력 → 같은 출력(순수 dict 변환·network/transport 주입 없음).
    a = build_operator_payload_authoring()
    b = build_operator_payload_authoring()
    assert a["payload_template"] == b["payload_template"]
    assert a["next_action"] == b["next_action"]


# ── 9. generated template cannot trigger live(gate 차단·integration) ───────────────────────────────────────
def test_generated_template_cannot_trigger_live():
    out = build_operator_payload_authoring()
    template = out["payload_template"]
    # 템플릿을 ADR#88 intake gate 에 넣어도 confirmed-live 가 되지 않는다(operator_confirmed=false).
    intake = run_operator_regulatory_event_intake(template)
    assert intake["operator_event_status"] != "confirmed_live"
    assert intake["operator_confirmed"] is False
    assert bool(intake["live_query_executed"]) is False
    # helper 자체 검증도 동일.
    nr = validate_template_not_real_payload(template)
    assert nr["can_trigger_live"] is False
    assert nr["is_real_payload"] is False


# ── placeholder seed(sec/fda/ofac) → named subject 지정 요구 ────────────────────────────────────────────────
def test_placeholder_seed_requires_named_subject():
    out = build_operator_payload_authoring(seed_id="sec_enforcement_settlement")
    # sec seed entity 는 'operator fills named respondent' → missing_fields 가 named subject 지정을 요구.
    joined = " ".join(out["missing_fields"]).lower()
    assert "respondent" in joined or "agency_or_entity" in joined


# ── missing_fields 가 발생 window 확인을 항상 요구(code-proposed 발생 미검증) ────────────────────────────────
def test_missing_fields_always_requires_occurrence_window_check():
    seed = _selected_seed()
    t = generate_operator_fillable_payload_template(seed)
    missing = emit_missing_fields_checklist(t, seed)
    assert any("occurrence window" in m.lower() for m in missing)


# ── no authorable seed → no_authorable_regulatory_seed(fail-closed) ────────────────────────────────────────
def test_no_authorable_seed_blocks():
    out = build_operator_payload_authoring(seed_id="does_not_exist")
    assert out["authoring_status"] == "no_authorable_regulatory_seed"
    assert out["payload_template_ready"] is False
    assert out["can_trigger_live"] is False
    assert out["payload_template"] is None
