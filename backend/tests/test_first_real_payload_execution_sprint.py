"""ADR#94 — first_real_payload_execution_sprint 테스트(fail-closed·단 한 번 gated live·network 0 except the one gated call).

검증: real payload 없음 → live 0 ∧ operator_confirmed_ready_package 생성(주입 acquisition_fn 미호출), 무효 → live 0,
valid ∧ approved ∧ executor=None → 호출 0, valid ∧ approved ∧ executor 주입 → 정확히 한 번 호출 ∧ live_query_executed
가 결과를 반영, expected provider 가시, raw payload 본문 미노출, sanitized 투영 strict subset, secret/PII 0.
"""
from __future__ import annotations

import json

from backend.app.tools.first_real_payload_execution_sprint import (
    OPERATION_NAME,
    SPRINT_AWAITING_PAYLOAD,
    SPRINT_LIVE_EXECUTED,
    SPRINT_PAYLOAD_INVALID,
    SPRINT_PAYLOAD_NOT_EXECUTED,
    build_first_real_payload_execution_sprint,
    main,
    sanitized_first_real_payload_execution_sprint,
)
from backend.app.tools.operator_regulatory_event_payload import (
    PAYLOAD_NOT_PROVIDED,
    PAYLOAD_PRESENT_INVALID_JSON,
    PAYLOAD_PRESENT_VALID,
)

_FORBIDDEN_KEYS = {"reviewer_name", "name", "email", "phone", "score", "model_score", "rationale",
                   "predicted_status", "raw_body", "body", "secret", "api_key", "provider_secret"}

_REQUIRED_KEYS = {
    "operation_name", "first_real_payload_sprint_status", "real_payload_present", "real_payload_valid",
    "selected_candidate_id", "operator_verification_required", "payload_required_fields", "real_payload_path",
    "validate_payload_command", "dry_run_command", "live_run_command", "expected_provider_calls", "provider_list",
    "bounded_live_policy", "next_action",
}

_INVARIANTS: dict[str, object] = {
    "routes_through_ungated_fidelity_probe": False,
    "raw_payload_text_exposed": False,
    "secret_values_exposed": False,
    "actual_sending_performed": False,
    "merge_allowed": False,
    "production_gold_count": 0,
}

# operator 확인·승인된 valid payload(epa seed·runner 테스트 _VALID_APPROVED 미러). confirmed_by 는 PII-성 마커(출력에 새면 안 됨).
_VALID_APPROVED = {
    "seed_id": "epa_final_rule_emissions",
    "operator_confirmed": True,
    "confirmed_by": "ops_lead_unique_marker_sprint",
    "confirmed_at": "2026-06-28",
    "agency_or_entity": "Environmental Protection Agency",
    "action_phrase": "final rule on greenhouse gas emissions standards",
    "date_window_start": "2026-06-25",
    "date_window_end": "2026-06-26",
    "official_query": "Environmental Protection Agency greenhouse gas emissions final rule",
    "news_query": "EPA emissions final rule reaction",
    "expected_news_angle": "industry and political reaction to the EPA final rule",
    "live_approved": True,
}


def _write_valid_payload(tmp_path) -> str:
    p = tmp_path / "operator_payload.json"
    p.write_text(json.dumps(_VALID_APPROVED), encoding="utf-8")
    return str(p)


def _fake_acq_factory():
    calls = []

    def fake_acq(seed, *, live_approved, today=None, **kw):
        calls.append({"seed": seed, "live_approved": live_approved})
        return {
            "official_news_live_status": "production_batch_frozen",
            "live_query_executed": True,
            "official_records_count": 3, "news_records_count": 2,
            "bridge_candidate_count": 2, "freeze_eligible_count": 1,
            "production_candidate_status": "frozen", "production_candidate_batch_ready": True,
            "production_frozen_pair_count": 1, "candidate_provenance": "live_official_news",
            "reviewer_handoff_ready": True, "production_gold_count": 0, "current_r1_gap": 200,
            "merge_allowed": False, "llm_invoked": False, "embedding_invoked": False, "db_write": False,
        }

    return fake_acq, calls


def _sentinel_acq(*_args, **_kwargs):
    raise AssertionError("acquisition_fn must NOT be called when there is no valid+approved real payload")


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
    out = build_first_real_payload_execution_sprint(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert _REQUIRED_KEYS <= set(out)
    assert out["operation_name"] == OPERATION_NAME
    for key, val in _INVARIANTS.items():
        assert out[key] is val if isinstance(val, bool) else out[key] == val


# ── missing payload blocks live AND creates operator_confirmed_ready_package (injected fn NOT called) ───────────
def test_missing_payload_blocks_live_and_creates_ready_package():
    out = build_first_real_payload_execution_sprint(
        operator_payload_status=PAYLOAD_NOT_PROVIDED, live_approved=True, acquisition_fn=_sentinel_acq)
    assert out["first_real_payload_sprint_status"] == SPRINT_AWAITING_PAYLOAD
    assert out["real_payload_present"] is False
    assert out["live_query_executed"] is False
    assert out["network_invoked"] is False
    assert out["blocked_reason"] == "missing_payload"
    # PRE-payload 묶음이 생성된다(operator 안내).
    pkg = out["operator_confirmed_ready_package"]
    assert isinstance(pkg, dict)
    assert pkg["operator_confirmed_ready_package_status"]
    assert pkg["operator_confirmed"] is False


def test_missing_payload_with_none_status_also_blocks():
    # operator_payload_status=None(이번 턴 기본·미주입) 도 present=False 로 판정한다.
    out = build_first_real_payload_execution_sprint(acquisition_fn=_sentinel_acq, live_approved=True)
    assert out["first_real_payload_sprint_status"] == SPRINT_AWAITING_PAYLOAD
    assert out["live_query_executed"] is False
    assert isinstance(out["operator_confirmed_ready_package"], dict)


# ── invalid payload blocks live (no call) ──────────────────────────────────────────────────────────────────────
def test_invalid_payload_blocks_live():
    out = build_first_real_payload_execution_sprint(
        operator_payload_status=PAYLOAD_PRESENT_INVALID_JSON, live_approved=True, acquisition_fn=_sentinel_acq)
    assert out["first_real_payload_sprint_status"] == SPRINT_PAYLOAD_INVALID
    assert out["real_payload_present"] is True
    assert out["real_payload_valid"] is False
    assert out["live_query_executed"] is False
    assert out["network_invoked"] is False


# ── valid + approved but acquisition_fn=None → no call (not executed) ───────────────────────────────────────────
def test_valid_approved_no_executor_does_not_execute():
    out = build_first_real_payload_execution_sprint(
        operator_payload_status=PAYLOAD_PRESENT_VALID, live_approved=True, acquisition_fn=None)
    assert out["first_real_payload_sprint_status"] == SPRINT_PAYLOAD_NOT_EXECUTED
    assert out["real_payload_valid"] is True
    assert out["live_query_executed"] is False
    assert out["network_invoked"] is False
    assert out["blocked_reason"] == "approved_but_no_executor"


# ── valid + present but NOT approved → no call (not executed) ───────────────────────────────────────────────────
def test_valid_not_approved_does_not_execute():
    fake_acq, calls = _fake_acq_factory()
    out = build_first_real_payload_execution_sprint(
        operator_payload_status=PAYLOAD_PRESENT_VALID, live_approved=False, acquisition_fn=fake_acq)
    assert out["first_real_payload_sprint_status"] == SPRINT_PAYLOAD_NOT_EXECUTED
    assert out["live_query_executed"] is False
    assert out["network_invoked"] is False
    assert len(calls) == 0
    assert out["blocked_reason"] == "not_approved"


# ── valid + approved + acquisition_fn provided → injected fn called EXACTLY ONCE, live_query_executed reflects result ──
def test_valid_approved_with_executor_calls_once(tmp_path):
    fake_acq, calls = _fake_acq_factory()
    path = _write_valid_payload(tmp_path)
    out = build_first_real_payload_execution_sprint(
        real_payload_path=path, operator_payload_status=PAYLOAD_PRESENT_VALID,
        live_approved=True, acquisition_fn=fake_acq)
    assert len(calls) == 1
    assert calls[0]["live_approved"] is True
    assert out["first_real_payload_sprint_status"] == SPRINT_LIVE_EXECUTED
    assert out["live_query_executed"] is True
    assert out["network_invoked"] is True
    assert out["operator_event_status"] == "confirmed_live_executed"
    assert out["reviewer_handoff_ready"] is True
    # 결과 경유에도 불변 유지(gold 0·merge 0·sending 0).
    assert out["production_gold_count"] == 0
    assert out["merge_allowed"] is False
    assert out["actual_sending_performed"] is False


# ── expected providers visible (int ≥1 · federal_register + guardian/nyt) ──────────────────────────────────────
def test_expected_providers_visible():
    out = build_first_real_payload_execution_sprint(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    n = out["expected_provider_calls"]
    assert isinstance(n, int) and not isinstance(n, bool)
    assert n == len(out["provider_list"]) >= 1
    assert "federal_register" in out["provider_list"]
    assert "guardian" in out["provider_list"]
    assert "nyt" in out["provider_list"]
    # bounded live policy: ungated fidelity probe 로 라우팅하지 않는다.
    assert out["bounded_live_policy"]["routes_through_ungated_fidelity_probe"] is False
    assert out["bounded_live_policy"]["routes_only_through_operator_confirmed_live_runner"] is True


# ── payload_required_fields surfaces the §8 required fields ─────────────────────────────────────────────────────
def test_payload_required_fields_present():
    out = build_first_real_payload_execution_sprint(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    fields = set(out["payload_required_fields"])
    assert {"operator_confirmed", "live_approved", "agency_or_entity", "action_phrase",
            "date_window_start", "date_window_end", "official_query", "news_query"} <= fields


# ── raw payload text not surfaced (valid path · confirmed_by marker absent) ────────────────────────────────────
def test_raw_payload_text_not_surfaced(tmp_path):
    fake_acq, _ = _fake_acq_factory()
    path = _write_valid_payload(tmp_path)
    out = build_first_real_payload_execution_sprint(
        real_payload_path=path, operator_payload_status=PAYLOAD_PRESENT_VALID,
        live_approved=True, acquisition_fn=fake_acq)
    dumped = json.dumps(out, default=str)
    assert "ops_lead_unique_marker_sprint" not in dumped
    assert out["raw_payload_text_exposed"] is False
    assert out["secret_values_exposed"] is False


# ── sanitized projection is a strict subset and exposes no raw payload (no commands/fields/policy) ──────────────
def test_sanitized_projection_strict_subset():
    out = build_first_real_payload_execution_sprint(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    s = sanitized_first_real_payload_execution_sprint(out)
    assert set(s).issubset(set(out))
    assert set(s) != set(out)
    for leaked in ("validate_payload_command", "dry_run_command", "live_run_command", "payload_required_fields",
                   "bounded_live_policy", "operator_confirmed_ready_package", "operator_verification_required"):
        assert leaked not in s


# ── no secret / PII anywhere in the output (both blocked and live paths) ───────────────────────────────────────
def test_no_secret_pii_in_output(tmp_path):
    out_block = build_first_real_payload_execution_sprint(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert set(_walk_keys(out_block)).isdisjoint(_FORBIDDEN_KEYS)
    fake_acq, _ = _fake_acq_factory()
    out_live = build_first_real_payload_execution_sprint(
        real_payload_path=_write_valid_payload(tmp_path), operator_payload_status=PAYLOAD_PRESENT_VALID,
        live_approved=True, acquisition_fn=fake_acq)
    assert set(_walk_keys(out_live)).isdisjoint(_FORBIDDEN_KEYS)


# ── CLI --json smoke (aggregate only · commands excluded) ──────────────────────────────────────────────────────
def test_main_json_smoke(capsys):
    rc = main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "first_real_payload_sprint_status" in captured.out
    assert "validate_payload_command" not in captured.out
    assert "bounded_live_policy" not in captured.out
