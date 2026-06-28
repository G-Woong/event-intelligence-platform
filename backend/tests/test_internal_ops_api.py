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
R1_PATH = "/api/internal/ops/r1-gold-acquisition"
R1_BATCH_PATH = "/api/internal/ops/r1-pilot-batch"
R1_PROD_PATH = "/api/internal/ops/r1-production-candidates"
R1_DISCRETE_PATH = "/api/internal/ops/r1-discrete-acquisition"
R1_BREADTH_PATH = "/api/internal/ops/r1-provider-breadth"
R1_BOUNDED_PATH = "/api/internal/ops/r1-bounded-live-breadth"


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


# ── ADR#74 /r1-gold-acquisition 엔드포인트(R1 gold floor gap + operator next action·read-only) ────────────
def test_r1_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    assert client.get(R1_PATH).status_code == 404


def test_r1_flag_on_returns_sanitized_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    r = client.get(R1_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract"] == "InternalOpsR1AcquisitionStatus"
    # 기본(무입력) → honest R1 blocked·gold 0/floor·gap=full target.
    assert body["r1_status"] == "blocked_no_labels"
    assert body["current_production_gold_count"] == 0
    assert body["required_production_gold_count"] == 200
    assert body["required_korean_gold_count"] == 50
    assert body["external_input_required"] is True


def test_r1_gap_visible_full_when_gold_zero(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_PATH).json()
    assert body["label_collection_gap"] == 200
    assert body["korean_gap"] == 50
    assert body["positive_gap"] == 67 and body["negative_gap"] == 67
    assert body["hard_negative_gap"] == 20
    assert body["reviewer_gap"] == 2
    # operator next manual action 가시(라벨 회수 수준).
    assert isinstance(body["next_manual_actions"], list) and body["next_manual_actions"]


def test_r1_no_go_flags_and_no_merge(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_PATH).json()
    for k in ("internal_only", "no_public_truth", "no_merge", "no_public_iu", "pii_safe", "no_llm", "no_db_write"):
        assert body["flags"][k] is True, k
    assert body["merge_gate_ready"] is False
    assert body["calibration_ready"] is False
    assert body["reviewer_agreement_required"] is True
    assert body["conflict_adjudication_required"] is True


def test_r1_no_forbidden_fields_and_no_pii(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_PATH).json()
    assert _forbidden_keys_in(body) == set()
    blob = json.dumps(body, ensure_ascii=False)
    assert "Users" not in blob          # 절대경로 미노출.


def test_r1_read_only_post_not_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    assert client.post(R1_PATH).status_code == 405


def test_r1_response_keys_are_sanitized_subset(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_PATH).json()
    allowed = {
        "contract", "r1_status", "actual_input_status", "external_input_required",
        "current_production_gold_count", "required_production_gold_count",
        "current_korean_gold_count", "required_korean_gold_count",
        "current_positive_gold_count", "current_negative_gold_count",
        "required_positive_gold_count", "required_negative_gold_count",
        "current_hard_negative_count", "required_hard_negative_count",
        "current_reviewer_count", "reviewer_count_required", "reviewer_duplication_required",
        "reviewer_agreement_required", "conflict_adjudication_required",
        "label_collection_gap", "korean_gap", "positive_gap", "negative_gap",
        "hard_negative_gap", "reviewer_gap", "calibration_ready", "merge_gate_ready",
        "next_manual_actions", "flags",
    }
    assert set(body) == allowed   # response_model 화이트리스트 — 추가 누출 0.


def test_r1_admin_auth_prod_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    c = TestClient(app)   # lifespan 미실행 — 요청 시점 인증만 검증(이중 게이트의 인증 축).
    assert c.get(R1_PATH).status_code == 503


# ── ADR#75 /r1-pilot-batch 엔드포인트(pilot batch freeze + launch readiness·read-only) ────────────────────
def test_r1_batch_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    assert client.get(R1_BATCH_PATH).status_code == 404


def test_r1_batch_flag_on_returns_sanitized_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    r = client.get(R1_BATCH_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract"] == "InternalOpsR1PilotBatchStatus"
    # 기본(무입력) → frozen 합성 pilot·production 후보 둔갑 0·launch ready·R1 blocked.
    assert body["batch_frozen"] is True
    assert body["candidate_provenance"] == "synthetic_fixture"
    assert body["pilot_batch_is_production_candidate"] is False
    assert body["launch_status"] == "ready_for_manual_launch"
    assert body["r1_status"] == "blocked_no_labels"


def test_r1_batch_launch_readiness_visible(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_BATCH_PATH).json()
    assert body["frozen_pair_count"] == 5            # captured fixture → 5 near-match pairs.
    assert body["target_pair_count"] == 200
    assert body["expected_label_file_count"] == 2
    assert body["returned_labels_found"] is False
    assert body["returned_label_count"] == 0
    assert body["ready_for_manual_launch"] is True
    assert body["current_r1_gap"] == 200
    assert body["r2_r7_no_go"] is True
    assert body["batch_signature"].startswith("sha256:")
    assert body["validation_command"]
    assert body["next_manual_action"]


def test_r1_batch_no_go_flags_and_no_merge(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_BATCH_PATH).json()
    for k in ("internal_only", "no_public_truth", "no_merge", "no_public_iu", "pii_safe", "no_llm", "no_db_write"):
        assert body["flags"][k] is True, k
    assert body["flags"]["gold_provenance_verified"] is False
    assert body["production_gold_count"] == 0


def test_r1_batch_no_forbidden_fields_and_no_pii(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_BATCH_PATH).json()
    assert _forbidden_keys_in(body) == set()
    blob = json.dumps(body, ensure_ascii=False)
    assert "Users" not in blob          # 절대경로/사용자명 미노출.


def test_r1_batch_read_only_post_not_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    assert client.post(R1_BATCH_PATH).status_code == 405


def test_r1_batch_response_keys_are_sanitized_subset(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_BATCH_PATH).json()
    allowed = {
        "contract", "pilot_batch_id", "batch_frozen", "batch_signature", "candidate_provenance",
        "pilot_batch_is_production_candidate", "frozen_pair_count", "target_pair_count",
        "expected_label_file_count", "launch_status", "ready_for_manual_launch", "returned_labels_found",
        "returned_label_count", "intake_directory", "validation_command", "r1_status",
        "production_gold_count", "required_production_gold_count", "current_r1_gap", "r2_r7_no_go",
        "next_manual_action", "flags",
    }
    assert set(body) == allowed   # response_model 화이트리스트 — 추가 누출 0.


def test_r1_batch_admin_auth_prod_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    c = TestClient(app)   # lifespan 미실행 — 요청 시점 인증만 검증(이중 게이트의 인증 축).
    assert c.get(R1_BATCH_PATH).status_code == 503


# ── ADR#76 /r1-production-candidates 엔드포인트(live acquisition + dual-track readiness·read-only) ─────────
def test_r1_prod_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    assert client.get(R1_PROD_PATH).status_code == 404


def test_r1_prod_flag_on_returns_sanitized_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    r = client.get(R1_PROD_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract"] == "InternalOpsR1ProductionCandidateStatus"
    # read API 는 live_query=False 고정(시도 0) → blocked(credential presence 에 따라 opt_in/credentials 둘 중 하나).
    assert body["production_candidate_status"] in ("blocked_no_live_opt_in", "blocked_no_credentials")
    assert body["live_call_performed"] is False
    assert body["production_candidate_batch_ready"] is False
    assert body["candidate_provenance"] == "none"
    assert body["blocked_no_live_production_candidates"] is True


def test_r1_prod_dual_track_separation_visible(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_PROD_PATH).json()
    # synthetic dry-run batch 와 production-candidate batch 가 분리·합성→production 둔갑 0.
    assert body["synthetic_dry_run_batch_ready"] is True
    assert body["synthetic_batch_not_production"] is True
    assert body["production_candidate_batch_ready"] is False
    assert body["live_candidate_count"] == 0
    assert body["publishable_pair_count"] == 0
    assert body["production_frozen_pair_count"] == 0
    assert body["required_production_gold_count"] == 200
    assert body["current_r1_gap"] == 200
    assert body["r2_r7_no_go"] is True
    assert body["next_manual_action"]


def test_r1_prod_no_go_flags_and_no_merge(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_PROD_PATH).json()
    for k in ("internal_only", "no_public_truth", "no_merge", "no_public_iu", "pii_safe", "no_llm", "no_db_write"):
        assert body["flags"][k] is True, k
    assert body["flags"]["gold_provenance_verified"] is False
    assert body["production_gold_count"] == 0


def test_r1_prod_no_forbidden_fields_and_no_pii(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_PROD_PATH).json()
    assert _forbidden_keys_in(body) == set()
    blob = json.dumps(body, ensure_ascii=False)
    assert "Users" not in blob          # 절대경로/사용자명 미노출.


def test_r1_prod_read_only_post_not_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    assert client.post(R1_PROD_PATH).status_code == 405


def test_r1_prod_response_keys_are_sanitized_subset(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_PROD_PATH).json()
    allowed = {
        "contract", "synthetic_dry_run_batch_ready", "synthetic_batch_not_production",
        "production_candidate_batch_ready", "production_candidate_status", "candidate_provenance",
        "live_call_performed", "live_candidate_count", "publishable_pair_count",
        "production_frozen_pair_count", "production_batch_id", "production_batch_signature",
        "ready_for_manual_launch", "blocked_no_live_production_candidates", "validation_command",
        "intake_directory", "r1_status", "production_gold_count", "required_production_gold_count",
        "current_r1_gap", "r2_r7_no_go", "next_manual_action", "flags",
    }
    assert set(body) == allowed   # response_model 화이트리스트 — 추가 누출 0.


def test_r1_prod_admin_auth_prod_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    c = TestClient(app)   # lifespan 미실행 — 요청 시점 인증만 검증(이중 게이트의 인증 축).
    assert c.get(R1_PROD_PATH).status_code == 503


# ── ADR#79 /r1-discrete-acquisition 엔드포인트(discrete-event acquisition + recall probe frontier·read-only) ──
def test_r1_discrete_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    assert client.get(R1_DISCRETE_PATH).status_code == 404


def test_r1_discrete_flag_on_returns_sanitized_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    r = client.get(R1_DISCRETE_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract"] == "InternalOpsDiscreteAcquisitionFrontier"
    # read API 는 live_query=False 고정(시도 0) → recall probe 는 synthetic 검증.
    assert body["recall_probe_applies_to_merge"] is False
    assert body["recall_probe_lever_demonstrated"] is True       # synthetic 에서 lever 작동.
    assert body["discrete_event_seed_source"] == "code_proposed_shape"
    assert body["live_candidate_count"] == 0


def test_r1_discrete_recall_probe_is_routing_signal_not_truth(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_DISCRETE_PATH).json()
    # recall probe = reviewer-routing only·merge 미적용·max 집계 신호만(per-pair score 미노출).
    assert body["recall_probe_applies_to_merge"] is False
    assert body["recall_probe_pairs_newly_routed"] >= 2          # 알려진 below-floor 같은-사건 lift.
    flags = body["flags"]
    for k in ("no_public_truth", "no_same_event_truth", "no_score", "no_rationale",
              "no_predicted_status", "no_raw_body", "no_secret"):
        assert flags[k] is True, k


def test_r1_discrete_required_copy_states_routing_only(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    copy = client.get(R1_DISCRETE_PATH).json()["required_copy"]
    assert any("reviewer-routing only" in c for c in copy)
    assert any("does not assert same-event" in c for c in copy)
    assert "R2~R7 remain No-Go" in copy


def test_r1_discrete_no_forbidden_fields_and_no_pii(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_DISCRETE_PATH).json()
    assert _forbidden_keys_in(body) == set()                    # score/rationale/predicted_status/raw PII 0.
    blob = json.dumps(body, ensure_ascii=False)
    assert "Users" not in blob                                  # 절대경로/사용자명 미노출.


def test_r1_discrete_read_only_post_not_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    assert client.post(R1_DISCRETE_PATH).status_code == 405


def test_r1_discrete_admin_auth_prod_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    c = TestClient(app)
    assert c.get(R1_DISCRETE_PATH).status_code == 503


def test_r1_discrete_response_keys_are_sanitized_subset(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_DISCRETE_PATH).json()
    allowed = {
        "contract", "discrete_event_seed_selected", "discrete_event_seed_source",
        "discrete_event_time_window", "discrete_seed_valid_count", "near_match_gap_status",
        "root_cause_hypotheses", "root_cause_confidence", "max_recall_probe_score",
        "recall_probe_pairs_newly_routed", "recall_probe_applies_to_merge",
        "recall_probe_lever_demonstrated",
        # ADR#80 live recall probe(aggregate only·per-pair score 미노출).
        "max_live_recall_probe_score", "live_pairs_newly_routed_by_probe",
        "live_recall_lift_status", "live_frontier_verdict",
        "live_candidate_count", "production_candidate_status",
        "blocked_reason", "provider_breadth_next_action", "korean_source_next_action",
        "current_r1_gap", "production_gold_count", "r2_r7_no_go", "required_copy", "flags",
    }
    assert set(body) == allowed   # response_model 화이트리스트 — 추가 누출 0(26 field·ADR#80 +4).


# ── ADR#81 /r1-provider-breadth 엔드포인트(provider breadth + named seed + KO path frontier·read-only) ──
def test_r1_breadth_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    assert client.get(R1_BREADTH_PATH).status_code == 404


def test_r1_breadth_flag_on_returns_sanitized_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    r = client.get(R1_BREADTH_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract"] == "InternalOpsProviderBreadthFrontier"
    # 실 registry 57 = 9 카테고리(분석 §2).
    assert body["query_capable_provider_count"] == 7
    assert body["feed_only_provider_count"] == 7
    assert body["ko_official_news_count"] == 6
    assert body["anchor_eligible_count"] == 25
    assert body["named_seed_count"] >= 2
    assert body["seed_type"] == "named_single_event"
    # read API 는 live_query=False 고정 → live_blocked_by_rate_or_opt_in 이 정상.
    assert body["live_recall_lift_status"] == "live_blocked_by_rate_or_opt_in"
    assert body["r2_r7_no_go"] is True


def test_r1_breadth_required_copy_states_support_not_truth(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    copy = client.get(R1_BREADTH_PATH).json()["required_copy"]
    assert "Provider breadth is acquisition support, not truth" in copy
    assert "Named seed is candidate generation, not same-event proof" in copy
    assert "Community reaction is not an event anchor" in copy
    assert "Production gold remains 0 until human labels are returned" in copy
    assert "R2~R7 remain No-Go" in copy


def test_r1_breadth_no_go_flags(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    flags = client.get(R1_BREADTH_PATH).json()["flags"]
    for k in ("no_public_truth", "no_same_event_truth", "no_score", "no_rationale",
              "no_predicted_status", "no_raw_body", "no_secret"):
        assert flags[k] is True, k


def test_r1_breadth_no_forbidden_fields_and_no_pii(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_BREADTH_PATH).json()
    assert _forbidden_keys_in(body) == set()                    # score/rationale/predicted_status/raw PII 0.
    blob = json.dumps(body, ensure_ascii=False)
    assert "Users" not in blob                                  # 절대경로/사용자명 미노출.


def test_r1_breadth_read_only_post_not_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    assert client.post(R1_BREADTH_PATH).status_code == 405


def test_r1_breadth_admin_auth_prod_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    c = TestClient(app)
    assert c.get(R1_BREADTH_PATH).status_code == 503


def test_r1_breadth_response_keys_are_sanitized_subset(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_BREADTH_PATH).json()
    allowed = {
        "contract", "provider_breadth_status", "provider_breadth_inventory_ready",
        "query_capable_provider_count", "feed_only_provider_count", "official_source_count",
        "search_url_candidate_count", "ko_official_news_count", "community_reaction_only_count",
        "market_signal_only_count", "catalog_enrichment_only_count", "unknown_quarantine_count",
        "anchor_eligible_count", "named_seed_bank_status", "named_seed_count",
        "selected_seed_for_next_live_run", "seed_type", "ko_source_path_status",
        "ko_tokenization_risk_recorded", "latest_live_seed", "live_recall_lift_status",
        "max_live_recall_probe_score", "newly_routed_count", "production_candidate_status",
        "blocked_reason", "current_r1_gap", "r2_r7_no_go", "acquisition_next_action",
        "required_copy", "flags",
    }
    assert set(body) == allowed   # response_model 화이트리스트 — 추가 누출 0(30 field).


# ── ADR#82 /r1-bounded-live-breadth 엔드포인트(bounded live run + date-pin gate + freeze attempt frontier·read-only) ──
def test_r1_bounded_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", False)
    assert client.get(R1_BOUNDED_PATH).status_code == 404


def test_r1_bounded_flag_on_returns_sanitized_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    r = client.get(R1_BOUNDED_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["contract"] == "InternalOpsBoundedLiveBreadthFrontier"
    # read API live_query=False 고정 + date-pin 미충족 → blocked.
    assert body["live_query_executed"] is False
    assert body["latest_bounded_live_run_status"] == "blocked_no_live_opt_in"
    assert body["named_seed_date_pin_status"].startswith("not_pinned")
    assert body["selected_seed_actual_occurrence"] is None
    assert body["blocked_reason"] == "missing_date_pinned_named_event"
    # bounded pool = adapter_wired ∩ credential(breadth 크기 아님) — 실 registry: guardian/nyt 만 wired.
    assert body["provider_breadth_used"] <= 2
    assert body["production_frozen_pair_count"] == 0
    assert body["production_gold_count"] == 0
    assert body["ko_floor_current"] == 0
    assert body["ko_floor_required"] == 50
    assert body["r2_r7_no_go"] is True


def test_r1_bounded_required_copy_states_live_needs_date_pin(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    copy = client.get(R1_BOUNDED_PATH).json()["required_copy"]
    assert "Provider breadth is acquisition support, not truth" in copy
    assert "A bounded live run requires an operator-confirmed date-pinned event" in copy
    assert "Production candidate freeze is a reviewer worklist, not same-event truth" in copy
    assert "Production gold remains 0 until human labels are returned" in copy
    assert "R2~R7 remain No-Go" in copy


def test_r1_bounded_no_go_flags(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    flags = client.get(R1_BOUNDED_PATH).json()["flags"]
    for k in ("no_public_truth", "no_same_event_truth", "no_score", "no_rationale",
              "no_predicted_status", "no_raw_body", "no_secret"):
        assert flags[k] is True, k


def test_r1_bounded_no_forbidden_fields_and_no_pii(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_BOUNDED_PATH).json()
    assert _forbidden_keys_in(body) == set()                    # score/rationale/predicted_status/raw PII 0.
    blob = json.dumps(body, ensure_ascii=False)
    assert "Users" not in blob                                  # 절대경로/사용자명 미노출.


def test_r1_bounded_read_only_post_not_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    assert client.post(R1_BOUNDED_PATH).status_code == 405


def test_r1_bounded_admin_auth_prod_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    c = TestClient(app)
    assert c.get(R1_BOUNDED_PATH).status_code == 503


def test_r1_bounded_response_keys_are_sanitized_subset(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_OPS_DASHBOARD_ENABLED", True)
    body = client.get(R1_BOUNDED_PATH).json()
    allowed = {
        "contract", "latest_bounded_live_run_status", "named_seed_selected",
        "named_seed_date_pin_status", "selected_seed_actual_occurrence", "live_query_approved",
        "live_query_executed", "live_call_count", "providers_used", "provider_breadth_used",
        "key_free_provider_count", "credential_required_provider_count", "comparison_pair_count",
        "max_recall_probe_score", "newly_routed_count", "production_candidate_status",
        "production_candidate_batch_ready", "production_frozen_pair_count", "sanitized_snapshot_status",
        "ko_source_lane_status", "ko_named_seed_needed", "ko_floor_current", "ko_floor_required",
        "blocked_reason", "acquisition_next_action", "current_r1_gap", "production_gold_count",
        "r2_r7_no_go", "required_copy", "flags",
    }
    assert set(body) == allowed   # response_model 화이트리스트 — 추가 누출 0(30 field).
