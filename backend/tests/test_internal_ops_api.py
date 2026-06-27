"""ADR#72 — internal ops dashboard read-only API 테스트(public truth 아님·read-only·이중 게이트).

커버: flag off→404·flag on→200 sanitized contract·no-go flags·forbidden field(score/rationale/predicted_status/
same_event/raw PII) 0·read-only(POST 405)·honest gold 0·prod fail-closed(admin-token 미설정→503·이중 게이트).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.security import require_admin_token
from backend.app.main import app
from backend.app.tools.reviewer_pilot_handoff import _HANDOFF_FORBIDDEN_KEYS

OPS_PATH = "/api/internal/ops/pilot-execution"
PREFLIGHT_PATH = "/api/internal/ops/preflight"


@pytest.fixture()
def client():
    # admin-token 의존성은 security.py 자체 테스트가 커버 — 여기선 flag/contract 거동에 집중(override 로 bypass).
    # lifespan 미실행(`with` 없음) — 이 엔드포인트는 DB/Milvus/Redis/OpenSearch 미사용이라 startup 서비스 연결
    # 불필요(미가동 서비스 연결 타임아웃 회피·빠름). 요청 경로는 filesystem 스캔 + 순수 ledger 만.
    app.dependency_overrides[require_admin_token] = lambda: None
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


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


def test_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    assert client.get(OPS_PATH).status_code == 404


def test_flag_on_returns_sanitized_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    r = client.get(OPS_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract"] == "InternalOpsPilotExecutionStatus"
    # 기본(queue 없음) → honest current state.
    assert body["execution_status"] == "not_started"
    assert body["pilot_status"] == "not_ready"


def test_flags_all_no_go(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    flags = client.get(OPS_PATH).json()["flags"]
    for k in ("internal_only", "no_public_truth", "no_merge", "no_public_iu", "pii_safe", "no_llm", "no_db_write"):
        assert flags[k] is True, k
    assert flags["gold_provenance_verified"] is False


def test_no_forbidden_fields_in_response(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(OPS_PATH).json()
    assert _forbidden_keys_in(body) == set()
    # same_event truth/raw 경로도 미노출.
    blob = json.dumps(body, ensure_ascii=False)
    assert "Users" not in blob


def test_read_only_post_not_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    assert client.post(OPS_PATH).status_code == 405   # GET only.


def test_honest_gold_zero_and_no_merge(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(OPS_PATH).json()
    assert body["production_gold_count"] == 0
    assert body["merge_gate_ready"] is False
    assert body["calibration_ready"] is False


def test_response_keys_are_sanitized_subset(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(OPS_PATH).json()
    allowed = {
        "contract", "batch_id", "pilot_status", "execution_status", "contact_evidence_present",
        "real_reviewers_contacted", "returned_label_count", "missing_label_count", "invalid_label_count",
        "invalid_file_count", "conflict_pair_count", "overdue_count", "production_gold_count",
        "synthetic_gold_count", "production_gold_provenance_verified", "calibration_ready",
        "merge_gate_ready", "next_action", "flags",
    }
    assert set(body) == allowed   # response_model 화이트리스트 — 추가 누출 0.


def test_admin_auth_prod_fail_closed(monkeypatch):
    # override 없이 실제 require_admin_token 강제. production + 토큰 미설정 → 503(이중 게이트의 인증 축·fail-closed).
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    c = TestClient(app)   # lifespan 미실행(startup auth posture RuntimeError 회피) — 요청 시점 인증만 검증.
    assert c.get(OPS_PATH).status_code == 503


def test_malformed_input_maps_to_503(client, monkeypatch):
    # malformed operator 입력 파일 등(ValueError/OSError) → 503·detail 에 원인 메시지/경로 미포함(`from None`).
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    import backend.app.api.internal_ops as ops_mod

    def boom():
        raise ValueError("malformed contact evidence file 'secret_path'")

    monkeypatch.setattr(ops_mod, "run_actual_input_gate", boom)
    r = client.get(OPS_PATH)
    assert r.status_code == 503
    assert "secret_path" not in r.text   # 경로/내용 누출 0.


# ── ADR#73 /preflight 엔드포인트(auth/deploy posture + R1~R7 readiness·read-only) ───────────────────────
def test_preflight_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    assert client.get(PREFLIGHT_PATH).status_code == 404


def test_preflight_flag_on_returns_sanitized_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    r = client.get(PREFLIGHT_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract"] == "InternalOpsPreflightStatus"
    assert body["preflight_status"] in {
        "disabled_safe", "enabled_internal_safe", "unsafe_public_exposure", "misconfigured", "unknown"}
    assert body["deployment_proven"] is False        # per-user auth 미증명 불변.
    assert body["public_nav_exposed"] is False
    assert body["r1_r7_readiness_matrix_ready"] is True
    assert len(body["r1_r7_stages"]) == 7


def test_preflight_no_forbidden_fields_and_no_token_value(client, monkeypatch):
    sentinel = "PREFLIGHT_TOKEN_SENTINEL_abc123"
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", sentinel)
    body = client.get(PREFLIGHT_PATH).json()
    assert _forbidden_keys_in(body) == set()
    blob = json.dumps(body, ensure_ascii=False)
    assert sentinel not in blob          # 토큰 값 미노출.
    assert "Users" not in blob           # 절대경로 미노출.
    assert body["admin_token_configured"] is True   # 존재 여부만.


def test_preflight_no_go_flags(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(PREFLIGHT_PATH).json()
    for k in ("internal_only", "no_public_truth", "no_merge", "no_public_iu", "pii_safe", "no_llm", "no_db_write"):
        assert body["flags"][k] is True, k
    assert body["merge_gate_ready"] is False
    assert body["production_gold_count"] == 0


def test_preflight_read_only_post_not_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    assert client.post(PREFLIGHT_PATH).status_code == 405


def test_preflight_admin_auth_prod_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    c = TestClient(app)   # lifespan 미실행 — 요청 시점 인증만 검증(이중 게이트의 인증 축).
    assert c.get(PREFLIGHT_PATH).status_code == 503
