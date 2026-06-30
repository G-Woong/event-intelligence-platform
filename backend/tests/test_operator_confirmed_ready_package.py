"""ADR#94 — operator_confirmed_ready_package 테스트(PRE-payload 묶음·코드가 confirm/approve/write 0·live 트리거 0·network 0).

검증: 이 묶음은 REAL payload 가 아니다(operator_confirmed/live_approved False), live 를 트리거할 수 없다(acquisition_fn
파라미터 0·live runner 호출 0·network_invoked False), occurrence/official source/news coverage 검증을 operator 에게
요구하고, real_payload_path 는 gitignored REAL_PAYLOAD_PATH 문자열이되 파일을 만들지 않으며, validate/live 명령은 문자열
로만 나오고, sanitized 투영은 strict subset(raw payload 미노출), secret/PII 0.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from backend.app.tools.operator_confirmed_ready_package import (
    OCRP_READY,
    OPERATION_NAME,
    build_operator_confirmed_ready_package,
    main,
    sanitized_operator_confirmed_ready_package,
)
from backend.app.tools.operator_regulatory_event_payload import REAL_PAYLOAD_PATH

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_KEYS = {"reviewer_name", "name", "email", "phone", "score", "model_score", "rationale",
                   "predicted_status", "raw_body", "body", "secret", "api_key", "provider_secret"}

_REQUIRED_KEYS = {
    "operation_name", "operator_confirmed_ready_package_status", "candidate_id", "candidate_summary",
    "official_query_draft", "news_query_draft", "date_window", "agency_or_entity", "action_phrase",
    "operator_must_verify_occurrence", "operator_must_verify_official_source", "operator_must_verify_news_coverage",
    "operator_must_set_operator_confirmed", "operator_must_set_live_approved", "real_payload_path",
    "validation_command", "live_command", "expected_provider_calls", "provider_list", "next_action",
}

_INVARIANTS: dict[str, object] = {
    "operator_confirmed": False,
    "live_approved": False,
    "same_event_asserted": False,
    "event_occurrence_verified_by_code": False,
    "code_writes_real_payload": False,
    "code_claims_event_occurred": False,
    "network_invoked": False,
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


# ── required keys + operation name + invariants ────────────────────────────────────────────────────────────────
def test_required_keys_and_invariants_present():
    out = build_operator_confirmed_ready_package()
    assert _REQUIRED_KEYS <= set(out)
    assert out["operation_name"] == OPERATION_NAME
    for key, val in _INVARIANTS.items():
        assert out[key] is val if isinstance(val, bool) else out[key] == val


# ── package is NOT a real payload (operator_confirmed/live_approved False) ──────────────────────────────────────
def test_package_is_not_a_real_payload():
    out = build_operator_confirmed_ready_package()
    assert out["operator_confirmed"] is False
    assert out["live_approved"] is False
    assert out["code_writes_real_payload"] is False
    assert out["code_claims_event_occurred"] is False
    assert out["event_occurrence_verified_by_code"] is False


# ── package cannot trigger live (no acquisition_fn param · no live runner call · network 0) ─────────────────────
def test_package_cannot_trigger_live():
    import backend.app.tools.operator_confirmed_ready_package as mod

    out = build_operator_confirmed_ready_package()
    assert out["network_invoked"] is False
    # build 시그니처에 acquisition_fn 이 없다(live 를 주입할 자리 없음).
    sig = inspect.signature(build_operator_confirmed_ready_package)
    assert "acquisition_fn" not in sig.parameters
    # 모듈 소스가 live runner 를 *호출*하지 않는다(명령은 문자열로만·실행 0).
    with open(mod.__file__, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "run_operator_confirmed_live(" not in text
    assert "import httpx" not in text
    assert "import requests" not in text


# ── occurrence verification required (truthy) ──────────────────────────────────────────────────────────────────
def test_occurrence_verification_required():
    out = build_operator_confirmed_ready_package()
    assert out["operator_must_verify_occurrence"]
    assert "occur" in str(out["operator_must_verify_occurrence"]).lower()


# ── official source verification required ───────────────────────────────────────────────────────────────────────
def test_official_source_verification_required():
    out = build_operator_confirmed_ready_package()
    assert out["operator_must_verify_official_source"]
    assert "official" in str(out["operator_must_verify_official_source"]).lower()


# ── news coverage verification required ─────────────────────────────────────────────────────────────────────────
def test_news_coverage_verification_required():
    out = build_operator_confirmed_ready_package()
    assert out["operator_must_verify_news_coverage"]
    assert "news" in str(out["operator_must_verify_news_coverage"]).lower()


# ── operator must set confirmed/approved (truthy instructions) ──────────────────────────────────────────────────
def test_operator_must_set_flags_present():
    out = build_operator_confirmed_ready_package()
    assert out["operator_must_set_operator_confirmed"]
    assert out["operator_must_set_live_approved"]
    fields = set(out["manual_confirmation_fields"])
    assert {"operator_confirmed", "live_approved"} <= fields


# ── real_payload_path is the gitignored REAL_PAYLOAD_PATH string and NO file is created at it ───────────────────
def test_real_payload_path_string_no_file_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = build_operator_confirmed_ready_package()
    assert isinstance(out["real_payload_path"], str)
    assert out["real_payload_path"] == REAL_PAYLOAD_PATH
    assert out["real_payload_path"] == "inputs/operator_events/operator_regulatory_event_payload.json"
    # build 는 real payload 를 쓰지 않는다(현재 cwd=tmp_path 에 어떤 파일/디렉터리도 만들지 않음).
    assert not (tmp_path / "inputs" / "operator_events").exists()
    assert out["code_writes_real_payload"] is False
    # real path 는 gitignored.
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "inputs/operator_events/" in gitignore


# ── validation/live commands present and are strings ───────────────────────────────────────────────────────────
def test_validation_and_live_commands_are_strings():
    out = build_operator_confirmed_ready_package()
    assert isinstance(out["validation_command"], str) and out["validation_command"]
    assert isinstance(out["live_command"], str) and out["live_command"]
    assert "operator_regulatory_event_payload" in out["validation_command"]
    assert "operator_confirmed_live_runner" in out["live_command"]


# ── candidate summary/query drafts come from the regulatory seed bank (default epa) ─────────────────────────────
def test_candidate_drafts_from_seed_bank():
    out = build_operator_confirmed_ready_package()
    assert out["operator_confirmed_ready_package_status"] == OCRP_READY
    assert out["candidate_id"] == "epa_final_rule_emissions"
    assert out["agency_or_entity"] == "Environmental Protection Agency"
    assert "emissions" in out["official_query_draft"].lower()
    assert "emissions" in out["news_query_draft"].lower()
    assert out["date_window"]["start"] and out["date_window"]["end"]
    # 요약은 발생을 단정하지 않는다(occurrence NOT verified).
    assert "NOT verified" in out["candidate_summary"]


# ── expected_provider_calls visible and an int ≥1 (== len(provider_list)) ──────────────────────────────────────
def test_expected_provider_calls_visible():
    out = build_operator_confirmed_ready_package()
    n = out["expected_provider_calls"]
    assert isinstance(n, int) and not isinstance(n, bool)
    assert n == len(out["provider_list"]) >= 1
    assert "federal_register" in out["provider_list"]
    assert "guardian" in out["provider_list"]
    assert "nyt" in out["provider_list"]


# ── sanitized projection is a strict subset and exposes no raw payload (no commands/drafts) ─────────────────────
def test_sanitized_projection_strict_subset():
    out = build_operator_confirmed_ready_package()
    s = sanitized_operator_confirmed_ready_package(out)
    assert set(s).issubset(set(out))
    assert set(s) != set(out)
    for leaked in ("validation_command", "live_command", "validate_payload_command", "live_run_command",
                   "candidate_summary", "official_query_draft", "news_query_draft", "manual_confirmation_fields"):
        assert leaked not in s


# ── no secret / PII anywhere in the output ─────────────────────────────────────────────────────────────────────
def test_no_secret_pii_in_output():
    out = build_operator_confirmed_ready_package()
    keys = set(_walk_keys(out))
    assert keys.isdisjoint(_FORBIDDEN_KEYS), keys & _FORBIDDEN_KEYS


# ── CLI --json smoke (aggregate only · commands/drafts excluded) ───────────────────────────────────────────────
def test_main_json_smoke(capsys):
    rc = main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "operator_confirmed_ready_package_status" in captured.out
    assert "validation_command" not in captured.out
    assert "candidate_summary" not in captured.out
