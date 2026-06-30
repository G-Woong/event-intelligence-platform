"""ADR#95 §11 (#22-27) — real_payload_file_template_hardening 테스트(template only·real 파일 생성 0·forbidden 거부·proof not-real)."""
from __future__ import annotations

import os

from backend.app.tools.operator_regulatory_event_intake import OPERATOR_EVENT_REQUIRED_FIELDS
from backend.app.tools.operator_regulatory_event_payload import (
    _PAYLOAD_FORBIDDEN_KEYS,
    EXAMPLE_PAYLOAD_PATH,
    REAL_PAYLOAD_PATH,
)
from backend.app.tools.real_payload_file_template_hardening import (
    CONTRACT_VERSION,
    OPERATION_NAME,
    TEMPLATE_HARDENED,
    build_real_payload_file_template_hardening,
    main,
    sanitized_real_payload_file_template_hardening,
    scan_payload_for_forbidden_keys,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe


def _build() -> dict:
    return build_real_payload_file_template_hardening()


# ── 1. lead keys + status ──────────────────────────────────────────────────────────────────────────────────
def test_lead_keys_and_status():
    out = _build()
    assert out["operation_name"] == OPERATION_NAME == "real_payload_file_template_hardening"
    assert out["contract_version"] == CONTRACT_VERSION == "real_payload_file_template_hardening_v1"
    assert out["payload_template_hardening_status"] == TEMPLATE_HARDENED == "payload_template_hardened"


# ── 2. template_schema default booleans operator_confirmed/live_approved == False ──────────────────────────
def test_template_schema_default_booleans_false():
    schema = _build()["template_schema"]
    assert isinstance(schema, dict)
    assert schema["operator_confirmed"] is False
    assert schema["live_approved"] is False


# ── 3. scan_payload_for_forbidden_keys rejects a secret key ────────────────────────────────────────────────
def test_scan_forbidden_keys_rejects_secret():
    assert scan_payload_for_forbidden_keys({"secret": "x", "agency_or_entity": "EPA"}) == ["secret"]


# ── 4. forbidden-key scan is recursive (any depth) ─────────────────────────────────────────────────────────
def test_scan_forbidden_keys_recursive():
    payload = {"a": {"b": [{"api_key": "v"}]}, "agency_or_entity": "EPA"}
    assert scan_payload_for_forbidden_keys(payload) == ["api_key"]


# ── 5. the hardened template_schema itself carries no forbidden keys ────────────────────────────────────────
def test_template_schema_has_no_forbidden_keys():
    assert scan_payload_for_forbidden_keys(_build()["template_schema"]) == []


# ── 6. required_fields lists all 12 OPERATOR_EVENT_REQUIRED_FIELDS ──────────────────────────────────────────
def test_required_fields_lists_all_twelve():
    out = _build()
    assert out["required_fields"] == list(OPERATOR_EVENT_REQUIRED_FIELDS)
    assert out["required_field_count"] == len(OPERATOR_EVENT_REQUIRED_FIELDS) == 12


# ── 7. forbidden_fields has 22 sorted entries == _PAYLOAD_FORBIDDEN_KEYS ────────────────────────────────────
def test_forbidden_fields_has_twentytwo():
    out = _build()
    assert out["forbidden_fields"] == sorted(_PAYLOAD_FORBIDDEN_KEYS)
    assert out["forbidden_field_count"] == len(_PAYLOAD_FORBIDDEN_KEYS) == 22


# ── 8. default_false_fields = only the booleans actually in the 12-field schema ────────────────────────────
def test_default_false_fields():
    out = _build()
    assert out["default_false_fields"] == ["operator_confirmed", "live_approved"]


# ── 9. build never writes the real payload file (disk write 0) ─────────────────────────────────────────────
def test_build_never_writes_real_payload_file():
    existed_before = os.path.exists(REAL_PAYLOAD_PATH)
    out = build_real_payload_file_template_hardening()
    assert out["real_file_written"] is False
    # build neither created nor deleted the real payload file.
    assert os.path.exists(REAL_PAYLOAD_PATH) == existed_before


# ── 10. validation_command non-empty & references the payload validation module ────────────────────────────
def test_validation_command_references_payload_module():
    cmd = _build()["validation_command"]
    assert cmd
    assert "operator_regulatory_event_payload" in cmd
    assert REAL_PAYLOAD_PATH in cmd


# ── 11. template_not_real_payload_proof proves the unfilled template is not a real payload ──────────────────
def test_template_not_real_payload_proof():
    proof = _build()["template_not_real_payload_proof"]
    assert proof["is_real_payload"] is False
    assert proof["can_trigger_live"] is False


# ── 12. hardcoded invariants + paths ───────────────────────────────────────────────────────────────────────
def test_invariants_and_paths():
    out = _build()
    assert out["real_file_written"] is False
    assert out["code_sets_operator_confirmed_true"] is False
    assert out["code_sets_live_approved_true"] is False
    assert out["real_payload_path_gitignored"] is True
    assert out["secret_values_exposed"] is False
    assert out["network_invoked"] is False
    assert out["production_gold_count"] == 0
    assert out["real_payload_path"] == REAL_PAYLOAD_PATH
    assert out["example_payload_path"] == EXAMPLE_PAYLOAD_PATH


# ── 13. no secret/PII at any depth (recursive guard passes) ────────────────────────────────────────────────
def test_pii_safe_passes():
    _assert_pii_safe(_build(), _path="test")   # raises on any forbidden key — must not raise.


# ── 14. sanitized projection carries status + aggregate flags ──────────────────────────────────────────────
def test_sanitized_has_status():
    agg = sanitized_real_payload_file_template_hardening(_build())
    assert agg["payload_template_hardening_status"] == TEMPLATE_HARDENED
    assert agg["required_field_count"] == 12
    assert agg["forbidden_field_count"] == 22
    assert agg["template_can_trigger_live"] is False
    assert "template_schema" not in agg   # aggregate-only(본문 제외).


# ── 15. CLI --json exits 0 ─────────────────────────────────────────────────────────────────────────────────
def test_main_json_exits_zero():
    assert main(["--json"]) == 0
