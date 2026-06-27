"""ADR#73 — internal ops auth/deploy preflight + R1~R7 readiness 테스트(공개 truth 아님·secret 0·no merge/LLM/DB).

커버: 5-state posture(disabled_safe/enabled_internal_safe/unsafe_public_exposure/misconfigured/unknown)·
dev+flag+무토큰→무인증 reachable·prod+무토큰→misconfigured·deployment_proven 불변 false·actual input 재확인·
R1~R7 matrix(7단계·provenance·public IU No-Go)·source role invariant·secret boundary(토큰 값 미노출)·
forbidden 필드 0·merge/LLM/embedding/DB 0.
"""
from __future__ import annotations

import json

from backend.app.core.config import settings
from backend.app.tools.internal_ops_preflight import (
    AUTH_BOUNDARY_HARDENED_PARTIAL,
    AUTH_BOUNDARY_NO_GO,
    POSTURE_DISABLED_SAFE,
    POSTURE_ENABLED_INTERNAL_SAFE,
    POSTURE_MISCONFIGURED,
    POSTURE_UNKNOWN,
    POSTURE_UNSAFE_PUBLIC_EXPOSURE,
    PREFLIGHT_STATES,
    R1_R7_READINESS,
    SOURCE_ROLE_INVARIANTS,
    _readiness_stage_summary,
    evaluate_internal_ops_posture,
    run_internal_ops_preflight,
)
from backend.app.tools.reviewer_pilot_handoff import _HANDOFF_FORBIDDEN_KEYS


def _forbidden_keys_in(obj) -> set:
    found: set = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _HANDOFF_FORBIDDEN_KEYS:
                    found.add(k)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return found


# ── §5 5-state posture(순수 평가·settings 주입) ─────────────────────────────────────────────────────────
def test_posture_disabled_safe_when_flag_off():
    # flag off → 어떤 env/토큰이든 disabled_safe(엔드포인트 404·가장 안전).
    for env in ("dev", "production"):
        p = evaluate_internal_ops_posture(app_env=env, dashboard_enabled=False, admin_token_configured=False)
        assert p["status"] == POSTURE_DISABLED_SAFE
        assert p["endpoint_open_unauthenticated"] is False


def test_posture_enabled_internal_safe_when_token_set():
    # flag on + 토큰 설정 → auth 강제(환경 무관) → enabled_internal_safe.
    for env in ("production", "dev"):
        p = evaluate_internal_ops_posture(app_env=env, dashboard_enabled=True, admin_token_configured=True)
        assert p["status"] == POSTURE_ENABLED_INTERNAL_SAFE
        assert p["endpoint_open_unauthenticated"] is False


def test_posture_misconfigured_prod_no_token():
    # flag on + 무토큰 + prod-like → 503/기동거부(서비스 불가·노출 아님) → misconfigured.
    for env in ("production", "staging"):
        p = evaluate_internal_ops_posture(app_env=env, dashboard_enabled=True, admin_token_configured=False)
        assert p["status"] == POSTURE_MISCONFIGURED
        assert p["endpoint_open_unauthenticated"] is False


def test_posture_unsafe_public_exposure_dev_no_token():
    # flag on + 무토큰 + dev/test → require_admin_token bypass → **무인증 reachable** → unsafe_public_exposure.
    for env in ("dev", "test"):
        p = evaluate_internal_ops_posture(app_env=env, dashboard_enabled=True, admin_token_configured=False)
        assert p["status"] == POSTURE_UNSAFE_PUBLIC_EXPOSURE
        assert p["endpoint_open_unauthenticated"] is True
        assert any("without_auth" in r for r in p["block_reasons"])


def test_posture_unknown_env():
    p = evaluate_internal_ops_posture(app_env="weird", dashboard_enabled=True, admin_token_configured=False)
    assert p["status"] == POSTURE_UNKNOWN


def test_all_posture_states_known():
    for env, flag, tok in [
        ("dev", False, False), ("production", True, True), ("production", True, False),
        ("dev", True, False), ("zzz", True, True),
    ]:
        p = evaluate_internal_ops_posture(app_env=env, dashboard_enabled=flag, admin_token_configured=tok)
        assert p["status"] in PREFLIGHT_STATES


def test_deployment_proven_always_false():
    # per-user auth 미구현 + 물리 reachability 미증명 → 어떤 posture 든 deployment_proven=False(완전종결 금지).
    for env, flag, tok in [("production", True, True), ("dev", False, False), ("dev", True, False)]:
        p = evaluate_internal_ops_posture(app_env=env, dashboard_enabled=flag, admin_token_configured=tok)
        assert p["deployment_proven"] is False


# ── run_internal_ops_preflight 통합(actual input 재확인 + posture + readiness) ───────────────────────────
def test_preflight_actual_input_rechecked_honest(monkeypatch):
    # 실 입력 0(canonical dir 부재) → no_actual_input·external_input_required·gold 0(정직).
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    out = run_internal_ops_preflight()
    assert out["actual_input_rechecked"] is True
    assert out["actual_input_status"] == "no_actual_input"
    assert out["external_input_required"] is True
    assert out["actual_contact_evidence_found"] is False
    assert out["actual_returned_labels_found"] is False
    assert out["production_gold_count"] == 0
    assert out["internal_ops_preflight_status"] == POSTURE_DISABLED_SAFE
    assert out["auth_boundary_status"] == AUTH_BOUNDARY_HARDENED_PARTIAL


def test_preflight_unsafe_exposure_rolls_up_no_go(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    out = run_internal_ops_preflight()
    assert out["internal_ops_preflight_status"] == POSTURE_UNSAFE_PUBLIC_EXPOSURE
    assert out["auth_boundary_status"] == AUTH_BOUNDARY_NO_GO
    assert out["endpoint_open_unauthenticated"] is True


def test_preflight_no_merge_no_llm_no_embedding_no_db(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    out = run_internal_ops_preflight()
    assert out["merge_allowed"] is False
    assert out["no_public_intelligence_unit"] is True
    assert out["db_write"] is False
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False
    assert out["merge_gate_ready"] is False
    assert out["public_truth_exposed"] is False
    assert out["same_event_truth_exposed"] is False
    assert out["raw_source_body_exposed"] is False
    assert out["public_nav_exposed"] is False


# ── §7 R1~R7 readiness matrix ───────────────────────────────────────────────────────────────────────────
def test_r1_r7_matrix_seven_stages_numbered():
    assert len(R1_R7_READINESS) == 7
    assert [s["stage"] for s in R1_R7_READINESS] == [f"R{i}" for i in range(1, 8)]


def test_r1_r7_every_stage_has_gate_fields():
    required = {"stage", "goal", "required_input", "current_status", "blocker",
                "forbidden_shortcut", "next_action", "test"}
    for s in R1_R7_READINESS:
        assert required <= set(s), f"{s['stage']} missing fields"
        assert s["current_status"] in {"FAIL", "No-Go"}


def test_r1_gold_floor_is_current_blocker():
    r1 = R1_R7_READINESS[0]
    assert r1["stage"] == "R1"
    assert r1["current_status"] == "FAIL"   # production_gold_count 0.
    assert "label" in r1["blocker"].lower()
    assert "synthetic" in r1["forbidden_shortcut"].lower() or "model" in r1["forbidden_shortcut"].lower()


def test_r1_r2_live_status_no_self_contradiction():
    # adversarial 6a: gold≥floor·merge_gate_ready → 정적 R1 FAIL 이 live PASS 로 파생(자기모순 차단).
    rows = _readiness_stage_summary(production_gold_count=200, calibration_ready=True, merge_gate_ready=True)
    by = {r["stage"]: r["current_status"] for r in rows}
    assert by["R1"] != "FAIL"     # gold 차면 R1 은 더 이상 FAIL 이 아니다.
    assert by["R1"] == "PASS"     # calibration_ready → PASS.
    assert by["R2"] == "PASS"     # merge_gate_ready → PASS.
    assert by["R7"] == "No-Go"    # R3~R7 은 런타임 미구축 → gold 무관 No-Go.
    # gold>0·미캘리브레이션 → R1 PARTIAL.
    part = {r["stage"]: r["current_status"]
            for r in _readiness_stage_summary(production_gold_count=5, calibration_ready=False)}
    assert part["R1"] == "PARTIAL"
    # gold 0(현재 baseline) → R1 FAIL(정직).
    zero = {r["stage"]: r["current_status"] for r in _readiness_stage_summary(production_gold_count=0)}
    assert zero["R1"] == "FAIL"


def test_r1_r7_matrix_ready_flag(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    out = run_internal_ops_preflight()
    assert out["r1_r7_readiness_matrix_ready"] is True
    assert len(out["r1_r7_stages"]) == 7
    # contract 표시용 trimmed 행은 forbidden_shortcut/test 미포함(안전 요약).
    assert set(out["r1_r7_stages"][0]) == {"stage", "goal", "current_status", "blocker", "next_action"}


def test_source_role_invariants_no_anchor():
    assert "reaction" in SOURCE_ROLE_INVARIANTS["community"]
    assert "not anchor" in SOURCE_ROLE_INVARIANTS["community"]
    assert "signal" in SOURCE_ROLE_INVARIANTS["market"]
    assert "enrichment" in SOURCE_ROLE_INVARIANTS["catalog"]
    assert "fail-closed" in SOURCE_ROLE_INVARIANTS["unknown"]
    assert "provenance" in SOURCE_ROLE_INVARIANTS["kg_edge"]
    assert "No-Go" in SOURCE_ROLE_INVARIANTS["public_iu"]


# ── secret/PII 경계 ─────────────────────────────────────────────────────────────────────────────────────
def test_secret_boundary_admin_token_value_never_exposed(monkeypatch):
    # 토큰 값을 sentinel 로 설정 → 출력 어디에도 값이 없어야(존재 여부 bool 만).
    sentinel = "TOPSECRET_ADMIN_TOKEN_SENTINEL_zzz999"
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", sentinel)
    out = run_internal_ops_preflight()
    blob = json.dumps(out, ensure_ascii=False, default=str)
    assert sentinel not in blob               # 값 미노출.
    assert out["admin_token_configured"] is True   # 존재 여부만.
    assert out["internal_ops_preflight_status"] == POSTURE_ENABLED_INTERNAL_SAFE


def test_preflight_output_has_no_forbidden_fields(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "x")
    out = run_internal_ops_preflight()
    assert _forbidden_keys_in(out) == set()
    # 절대경로 사용자명 등 미노출.
    assert "Users" not in json.dumps(out, ensure_ascii=False, default=str)


def test_preflight_contract_sanitized_subset(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    out = run_internal_ops_preflight()
    c = out["preflight_contract"]
    allowed = {
        "contract", "preflight_status", "auth_boundary_status", "app_env", "admin_token_required",
        "admin_token_configured", "feature_flag_required", "feature_flag_enabled",
        "frontend_server_env_required", "public_nav_exposed", "deployment_proven", "actual_input_status",
        "external_input_required", "production_gold_count", "calibration_ready", "merge_gate_ready",
        "r1_r7_readiness_matrix_ready", "r1_r7_stages", "flags", "block_reasons", "next_actions",
    }
    assert set(c) == allowed
    assert c["contract"] == "InternalOpsPreflightStatus"
