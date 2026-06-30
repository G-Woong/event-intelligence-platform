"""ADR#93 §9 — real_payload_promotion_workflow 테스트(승격 후보 → REAL payload draft 절차·코드가 confirm/approve/write 0).

검증(§20 #8-#15): 선택 후보는 draft 로 남고(operator_confirmed/live_approved 강제 False), 코드가 confirmed/approved 를
설정하지 않으며, occurrence 확인이 체크리스트 FIRST 이고, real path 가 gitignored 로 노출되며, validation/preflight/
manual live 명령이 *수동 단계*로만 나오고, network 0·real payload 파일 생성 0. real-present/no-candidate 분기도 검증.
"""
from __future__ import annotations

from pathlib import Path

from backend.app.tools.operator_regulatory_event_payload import (
    PAYLOAD_NOT_PROVIDED,
    PAYLOAD_PRESENT_INVALID_JSON,
    PAYLOAD_PRESENT_VALID,
    REAL_PAYLOAD_PATH,
)
from backend.app.tools.real_payload_promotion_workflow import (
    OPERATION_NAME,
    RPP_DRAFT_READY,
    RPP_NO_CANDIDATE,
    RPP_REAL_PRESENT,
    build_real_payload_promotion_workflow,
    main,
    sanitized_real_payload_promotion,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_KEYS = {"secret", "api_key", "reviewer_name", "email", "phone", "score", "rationale",
                   "predicted_status", "raw_body", "body", "model_score"}

_REQUIRED_KEYS = {
    "operation_name", "real_payload_promotion_status", "selected_attempt_candidate_id",
    "operator_verification_required", "manual_confirmation_fields", "real_payload_path",
    "example_payload_path", "promotion_checklist", "validation_command",
    "live_preflight_command", "manual_live_command", "safety_notes", "next_action",
}

# hardcoded honesty invariants(EVERY input 에서 정확히 이 값).
_INVARIANTS: dict[str, object] = {
    "code_sets_operator_confirmed_true": False,
    "code_sets_live_approved_true": False,
    "code_claims_event_occurred": False,
    "code_writes_real_payload": False,
    "draft_operator_confirmed": False,
    "draft_live_approved": False,
    "real_payload_path_gitignored": True,
    "same_event_asserted": False,
    "actual_sending_performed": False,
    "merge_allowed": False,
    "production_gold_count": 0,
}


def _walk_keys(obj: object):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


# ── required keys + operation name ────────────────────────────────────────────────────────────────────────────
def test_required_output_keys_present():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert _REQUIRED_KEYS <= set(out)
    assert out["operation_name"] == OPERATION_NAME


# ── §20-8: selected candidate remains a draft (default selection prefers epa) ──────────────────────────────────
def test_08_selected_candidate_remains_draft():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["real_payload_promotion_status"] == RPP_DRAFT_READY
    assert out["selected_attempt_candidate_id"] == "epa_final_rule_emissions"
    assert out["draft_operator_confirmed"] is False
    assert out["draft_live_approved"] is False
    assert out["draft_can_trigger_live"] is False


def test_explicit_candidate_selection():
    out = build_real_payload_promotion_workflow(
        selected_attempt_candidate_id="sec_enforcement_settlement",
        operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["selected_attempt_candidate_id"] == "sec_enforcement_settlement"
    assert out["real_payload_promotion_status"] == RPP_DRAFT_READY


def test_unknown_candidate_falls_back_to_default():
    out = build_real_payload_promotion_workflow(
        selected_attempt_candidate_id="does_not_exist",
        operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["selected_attempt_candidate_id"] == "epa_final_rule_emissions"


# ── §20-9: promotion never sets operator_confirmed true ────────────────────────────────────────────────────────
def test_09_never_sets_operator_confirmed_true():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["code_sets_operator_confirmed_true"] is False
    assert out["draft_operator_confirmed"] is False
    assert out["operator_verification_required"]["draft_confirmation_valid"] is False


# ── §20-10: promotion never sets live_approved true ────────────────────────────────────────────────────────────
def test_10_never_sets_live_approved_true():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["code_sets_live_approved_true"] is False
    assert out["draft_live_approved"] is False
    assert out["operator_verification_required"]["draft_live_eligible"] is False


# ── §20-11: occurrence verification present in checklist AND first (before approval flags) ──────────────────────
def test_11_occurrence_verification_first_in_checklist():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    checklist = out["promotion_checklist"]
    assert any("occur" in s.lower() for s in checklist)
    verify_idx = next(i for i, s in enumerate(checklist) if "occur" in s.lower())
    confirm_idx = next(i for i, s in enumerate(checklist) if "operator_confirmed=true" in s)
    assert verify_idx == 0
    assert verify_idx < confirm_idx
    assert out["operator_verification_required"]["must_verify_occurrence_first"] is True


def test_manual_confirmation_fields_contract():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    fields = set(out["manual_confirmation_fields"])
    assert {"operator_confirmed", "confirmed_by", "confirmed_at",
            "date_window_start", "date_window_end", "live_approved"} <= fields


# ── §20-12: real_payload_path shown and gitignored ─────────────────────────────────────────────────────────────
def test_12_real_payload_path_shown_and_gitignored():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["real_payload_path"] == REAL_PAYLOAD_PATH
    assert out["real_payload_path"] == "inputs/operator_events/operator_regulatory_event_payload.json"
    assert out["real_payload_path_gitignored"] is True
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "inputs/operator_events/" in gitignore


# ── §20-13: validation_command emitted (and preflight is the no-live alias) ────────────────────────────────────
def test_13_validation_command_emitted():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["validation_command"]
    assert "operator_regulatory_event_payload" in out["validation_command"]
    assert REAL_PAYLOAD_PATH in out["validation_command"]
    # live_preflight_command 는 validation_command 의 alias(별도 live 실행 없음).
    assert out["live_preflight_command"] == out["validation_command"]


# ── §20-14: manual_live_command emitted as a manual step only ──────────────────────────────────────────────────
def test_14_manual_live_command_is_manual_step():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["manual_live_command"]
    assert "operator_confirmed_live_runner" in out["manual_live_command"]
    assert out["live_command_is_manual_step"] is True
    # 체크리스트의 마지막(4번) 단계로만 등장.
    assert any("operator_confirmed_live_runner" in s for s in out["promotion_checklist"])


# ── §20-15: no network / no file created under inputs/operator_events ───────────────────────────────────────────
def test_15_no_network_no_real_payload_write(tmp_path, monkeypatch):
    import sys

    import backend.app.tools.real_payload_promotion_workflow as mod

    monkeypatch.chdir(tmp_path)
    http_clients = {"httpx", "requests", "aiohttp", "urllib3"}
    before = http_clients & set(sys.modules)
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    after = http_clients & set(sys.modules)

    assert out["code_writes_real_payload"] is False
    assert after == before, "build loaded an http client (network risk)"
    # 어떤 real payload 파일/디렉터리도 생성하지 않는다(현재 cwd=tmp_path).
    assert not (tmp_path / "inputs" / "operator_events").exists()
    # 모듈 소스 회귀 방어(http client import 0).
    with open(mod.__file__, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "import httpx" not in text
    assert "import requests" not in text


# ── real-present branch: promotion complete ────────────────────────────────────────────────────────────────────
def test_real_present_branch_promotion_complete():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_PRESENT_VALID)
    assert out["real_payload_promotion_status"] == RPP_REAL_PRESENT
    # real 이 있어도 코드 정직 불변은 동일.
    assert out["code_writes_real_payload"] is False
    assert out["code_sets_operator_confirmed_true"] is False
    assert "already present" in out["next_action"]


# ── no-candidate branch (pack 이 후보 0 일 때만 도달 — entry 로는 비도달, monkeypatch 로 분기 검증) ──────────────
def test_no_candidate_branch(monkeypatch):
    import backend.app.tools.real_payload_promotion_workflow as mod

    def _empty_pack(**_kwargs):
        return {
            "live_attempt_pack_status": mod.PACK_NO_CANDIDATES,
            "available_candidate_ids": [],
            "attempt_pack_id": mod.ATTEMPT_PACK_ID,
            "candidate_event_shapes": [],
        }

    monkeypatch.setattr(mod, "build_live_attempt_pack", _empty_pack)
    out = mod.build_real_payload_promotion_workflow()
    assert out["real_payload_promotion_status"] == RPP_NO_CANDIDATE
    assert out["selected_attempt_candidate_id"] is None
    assert out["manual_confirmation_fields"]  # 키는 여전히 존재.
    assert "no attempt candidate" in out["next_action"]


# ── operator_verification_required surfaces the failed live gate ───────────────────────────────────────────────
def test_operator_verification_required_draft_fails_gate():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    ov = out["operator_verification_required"]
    assert ov["required"] is True
    assert ov["draft_confirmation_valid"] is False
    assert ov["draft_live_eligible"] is False
    assert ov["must_verify_occurrence_first"] is True
    # gate 실패 사유가 표면화된다(operator 가 채워야 할 결손).
    assert ov["blocked_reason"]


# ── honesty invariants present with exact values on EVERY input ────────────────────────────────────────────────
def test_honesty_invariants_on_every_input():
    for status in (PAYLOAD_NOT_PROVIDED, PAYLOAD_PRESENT_VALID, PAYLOAD_PRESENT_INVALID_JSON, None):
        out = build_real_payload_promotion_workflow(operator_payload_status=status)
        for key, val in _INVARIANTS.items():
            if isinstance(val, bool):
                assert out[key] is val, f"{key} must be {val} for status={status}"
            else:
                assert out[key] == val, f"{key} must be {val} for status={status}"


# ── no secret/PII anywhere in the output ───────────────────────────────────────────────────────────────────────
def test_no_secret_pii_in_output():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    keys = set(_walk_keys(out))
    assert keys.isdisjoint(_FORBIDDEN_KEYS), keys & _FORBIDDEN_KEYS


# ── safety_notes present (invariant operator guidance) ─────────────────────────────────────────────────────────
def test_safety_notes_present():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert len(out["safety_notes"]) >= 5
    assert any("gitignored" in n for n in out["safety_notes"])
    assert any("never sets operator_confirmed=true" in n for n in out["safety_notes"])


# ── sanitized projection (aggregate-only·체크리스트/명령 제외) ──────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_real_payload_promotion_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    s = sanitized_real_payload_promotion(out)
    assert set(s.keys()) == {
        "real_payload_promotion_status", "selected_attempt_candidate_id",
        "code_sets_operator_confirmed_true", "code_sets_live_approved_true",
        "code_writes_real_payload", "draft_operator_confirmed", "draft_live_approved",
        "real_payload_path_gitignored", "production_gold_count", "real_payload_promotion_next_action",
    }
    assert "promotion_checklist" not in s
    assert "validation_command" not in s
    assert "manual_live_command" not in s
    assert s["real_payload_promotion_status"] == out["real_payload_promotion_status"]
    assert s["real_payload_promotion_next_action"] == out["next_action"]


# ── CLI --json smoke (aggregate only) ──────────────────────────────────────────────────────────────────────────
def test_main_json_smoke(capsys):
    rc = main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "real_payload_promotion_status" in captured.out
    assert "promotion_checklist" not in captured.out
