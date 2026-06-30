"""ADR#89 §19(6~18) — operator regulatory event payload entrypoint(real↔example 분리·gitignored·PII fail-closed·
live 게이트). real payload 주입 + fake acquisition_fn 으로 결정론 검증(network 0)."""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.tools.operator_regulatory_event_intake import OPERATOR_EVENT_REQUIRED_FIELDS
from backend.app.tools.operator_regulatory_event_payload import (
    EXAMPLE_OPERATOR_REGULATORY_EVENT_PAYLOAD,
    EXAMPLE_PAYLOAD_PATH,
    PAYLOAD_NOT_PROVIDED,
    PAYLOAD_PRESENT_INVALID_JSON,
    PAYLOAD_PRESENT_PII_OR_SECRET,
    PAYLOAD_PRESENT_VALID,
    REAL_PAYLOAD_GITIGNORE_PREFIX,
    is_example_payload,
    load_operator_regulatory_event_payload,
    resolve_operator_payload_entrypoint,
    run_operator_confirmed_live_if_allowed,
    validate_operator_regulatory_event_payload,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

VALID_PAYLOAD = {
    "seed_id": "epa_final_rule_emissions",
    "operator_confirmed": True,
    "confirmed_by": "ops_lead_role",
    "confirmed_at": "2026-06-25",
    "agency_or_entity": "Environmental Protection Agency",
    "action_phrase": "final rule tightening greenhouse gas emissions standards",
    "date_window_start": "2026-06-25",
    "date_window_end": "2026-06-26",
    "official_query": "EPA greenhouse gas emissions final rule",
    "news_query": "EPA emissions rule industry reaction",
    "expected_news_angle": "industry and states react to the EPA emissions rule",
    "live_approved": True,
}


def _fake_acq(calls: list):
    def _acq(seed, *, live_approved=False, today=None, **kw):
        calls.append({"seed": seed, "live_approved": live_approved, "today": today})
        return {
            "official_news_live_status": "official_news_bridge_candidates_found",
            "live_query_executed": True,
            "official_records_count": 3, "news_records_count": 5,
            "bridge_candidate_count": 1, "freeze_eligible_count": 1,
            "production_candidate_status": "live_candidates_found",
            "production_candidate_batch_ready": False, "production_frozen_pair_count": 0,
            "candidate_provenance": "live_official_news", "reviewer_handoff_ready": False,
            "production_gold_count": 0, "current_r1_gap": 200,
            "merge_allowed": False, "llm_invoked": False, "embedding_invoked": False, "db_write": False,
        }
    return _acq


def _write(tmp_path: Path, payload) -> str:
    p = tmp_path / "operator_regulatory_event_payload.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


# ── §19-6: missing payload file → not_provided ─────────────────────────────────────────────────────────────
def test_06_missing_payload_file_not_provided(tmp_path):
    out = resolve_operator_payload_entrypoint(str(tmp_path / "does_not_exist.json"))
    assert out["operator_payload_status"] == PAYLOAD_NOT_PROVIDED
    assert out["operator_payload_path_status"] == "example_only_no_real_payload"
    assert out["operator_event_status"] == "not_provided"
    assert out["live_query_executed"] is False
    assert out["production_gold_count"] == 0


# ── §19-7: invalid JSON rejected ────────────────────────────────────────────────────────────────────────────
def test_07_invalid_json_rejected(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    loaded = load_operator_regulatory_event_payload(str(p))
    assert loaded["operator_payload_status"] == PAYLOAD_PRESENT_INVALID_JSON
    assert loaded["payload"] is None
    # entrypoint: invalid file → no live, not_provided event status (payload dropped fail-closed).
    out = resolve_operator_payload_entrypoint(str(p))
    assert out["operator_payload_status"] == PAYLOAD_PRESENT_INVALID_JSON
    assert out["live_query_executed"] is False


# ── §19-8: secret-like field rejected fail-closed ──────────────────────────────────────────────────────────
def test_08_secret_field_rejected_fail_closed(tmp_path):
    payload = {**VALID_PAYLOAD, "guardian_api_key": "sk-should-never-be-here"}
    p = _write(tmp_path, payload)
    loaded = load_operator_regulatory_event_payload(p)
    assert loaded["operator_payload_status"] == PAYLOAD_PRESENT_PII_OR_SECRET
    assert loaded["payload"] is None   # fail-closed: payload 폐기.
    assert "guardian_api_key" in loaded["forbidden_keys_found"]
    # entrypoint never goes live with a rejected payload.
    out = resolve_operator_payload_entrypoint(p)
    assert out["operator_payload_status"] == PAYLOAD_PRESENT_PII_OR_SECRET
    assert out["payload_forbidden_keys_count"] >= 1
    assert out["live_query_executed"] is False


# ── §19-9: reviewer PII rejected ────────────────────────────────────────────────────────────────────────────
def test_09_reviewer_pii_rejected(tmp_path):
    payload = {**VALID_PAYLOAD, "reviewer_email": "someone@example.com"}
    p = _write(tmp_path, payload)
    loaded = load_operator_regulatory_event_payload(p)
    assert loaded["operator_payload_status"] == PAYLOAD_PRESENT_PII_OR_SECRET
    assert "reviewer_email" in loaded["forbidden_keys_found"]
    assert loaded["payload"] is None


# ── §19-8/9 보강: 임의 depth(dict/list 재귀) nested forbidden 키도 fail-closed(code-review MINOR-1·adversarial F3) ──
def test_09b_nested_forbidden_key_rejected(tmp_path):
    # depth-1 nested dict.
    payload = {**VALID_PAYLOAD, "metadata": {"api_key": "sk-nested-should-never-be-here"}}
    p = _write(tmp_path, payload)
    loaded = load_operator_regulatory_event_payload(p)
    assert loaded["operator_payload_status"] == PAYLOAD_PRESENT_PII_OR_SECRET
    assert "api_key" in loaded["forbidden_keys_found"]   # 키명만(값 미노출).
    assert loaded["payload"] is None
    # entrypoint 도 live 미실행.
    out = resolve_operator_payload_entrypoint(p)
    assert out["payload_forbidden_keys_count"] >= 1
    assert out["live_query_executed"] is False


def test_09c_deeply_nested_and_list_forbidden_key_rejected(tmp_path):
    # depth-2 dict-in-dict + list-in-dict — 전 depth 재귀 scan 잠금(adversarial Finding 3).
    deep = {**VALID_PAYLOAD, "extra": {"inner": {"secret": "value-never-read"}}}
    p1 = _write(tmp_path, deep)
    loaded1 = load_operator_regulatory_event_payload(p1)
    assert loaded1["operator_payload_status"] == PAYLOAD_PRESENT_PII_OR_SECRET
    assert "secret" in loaded1["forbidden_keys_found"]
    assert loaded1["payload"] is None

    listed = {**VALID_PAYLOAD, "notes": [{"ok": 1}, {"model_score": 0.9}]}
    p2 = tmp_path / "listed.json"
    p2.write_text(json.dumps(listed), encoding="utf-8")
    loaded2 = load_operator_regulatory_event_payload(str(p2))
    assert loaded2["operator_payload_status"] == PAYLOAD_PRESENT_PII_OR_SECRET
    assert "model_score" in loaded2["forbidden_keys_found"]
    assert loaded2["payload"] is None


# ── §19-10: operator_confirmed=false blocks live ───────────────────────────────────────────────────────────
def test_10_operator_not_confirmed_blocks_live():
    calls: list = []
    payload = {**VALID_PAYLOAD, "operator_confirmed": False}
    out = run_operator_confirmed_live_if_allowed(payload, acquisition_fn=_fake_acq(calls))
    assert out["operator_event_status"] == "operator_not_confirmed"
    assert out["official_news_live_status"] == "blocked_operator_not_confirmed"
    assert calls == []   # engine 미호출.


# ── §19-11: live_approved=false blocks live ─────────────────────────────────────────────────────────────────
def test_11_live_not_approved_blocks_live():
    calls: list = []
    payload = {**VALID_PAYLOAD, "live_approved": False}
    out = run_operator_confirmed_live_if_allowed(payload, acquisition_fn=_fake_acq(calls))
    assert out["operator_event_status"] == "confirmed_not_approved"
    assert out["official_news_live_status"] == "blocked_no_live_opt_in"
    assert calls == []   # engine 미호출(network 0).


# ── §19-12: valid payload accepted ──────────────────────────────────────────────────────────────────────────
def test_12_valid_payload_accepted():
    cv = validate_operator_regulatory_event_payload(VALID_PAYLOAD)
    assert cv["confirmation_valid"] is True
    assert cv["operator_confirmed"] is True
    assert cv["same_event_asserted"] is False   # 확인은 truth 아님.


# ── §19-13: example payload not treated as real payload ────────────────────────────────────────────────────
def test_13_example_payload_not_real(tmp_path):
    assert is_example_payload(EXAMPLE_OPERATOR_REGULATORY_EVENT_PAYLOAD) is True
    # example 이 real 경로에 잘못 놓여도 operator_confirmed=false 라 live 차단.
    p = _write(tmp_path, EXAMPLE_OPERATOR_REGULATORY_EVENT_PAYLOAD)
    out = resolve_operator_payload_entrypoint(p)
    assert out["payload_is_example_dummy"] is True
    assert out["operator_event_status"] in ("operator_not_confirmed", "invalid_confirmation")
    assert out["live_query_executed"] is False


# ── §19-14: real payload path is gitignored ────────────────────────────────────────────────────────────────
def test_14_real_payload_path_gitignored():
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert REAL_PAYLOAD_GITIGNORE_PREFIX in gitignore
    out = resolve_operator_payload_entrypoint(None)
    assert out["real_payload_gitignored"] is True
    assert out["code_generated_payload"] is False


# ── §19-15: code_proposed seed not promoted to confirmed ───────────────────────────────────────────────────
def test_15_code_proposed_not_promoted():
    # operator_confirmed 누락(= code_proposed shape only) → confirmation invalid·provenance code_proposed.
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "operator_confirmed"}
    cv = validate_operator_regulatory_event_payload(payload)
    assert cv["confirmation_valid"] is False
    assert cv["seed_provenance"] == "code_proposed_regulatory_shape"


# ── §19-16: valid∧approved payload calls engine (via fake acquisition_fn) ───────────────────────────────────
def test_16_valid_approved_calls_engine(tmp_path):
    calls: list = []
    p = _write(tmp_path, VALID_PAYLOAD)
    out = resolve_operator_payload_entrypoint(p, acquisition_fn=_fake_acq(calls))
    assert out["operator_payload_status"] == PAYLOAD_PRESENT_VALID
    assert out["operator_event_status"] == "confirmed_live_executed"
    assert len(calls) == 1                       # engine 정확히 1회 호출.
    assert calls[0]["live_approved"] is True
    assert calls[0]["seed"]["provenance"] == "operator_confirmed_event"
    assert out["live_query_executed"] is True
    assert out["bridge_candidate_count"] == 1
    assert out["production_gold_count"] == 0     # freeze 후보 있어도 gold 0.


# ── §19-17: invalid payload does not call engine ───────────────────────────────────────────────────────────
def test_17_invalid_payload_no_engine():
    calls: list = []
    payload = {**VALID_PAYLOAD, "agency_or_entity": "agency"}   # generic → invalid.
    out = run_operator_confirmed_live_if_allowed(payload, acquisition_fn=_fake_acq(calls))
    assert out["operator_event_status"] == "invalid_confirmation"
    assert out["official_news_live_status"] == "blocked_invalid_confirmation"
    assert calls == []


# ── §19-18: blocked_no_live_opt_in does not call network ───────────────────────────────────────────────────
def test_18_no_opt_in_no_network():
    calls: list = []
    payload = {**VALID_PAYLOAD, "live_approved": False}
    out = run_operator_confirmed_live_if_allowed(payload, acquisition_fn=_fake_acq(calls))
    assert out["live_query_executed"] is False
    assert calls == []


# ── 추가: example 파일이 12 required 필드 + operator_confirmed=false(real 아님) ─────────────────────────────
def test_example_file_is_committed_template():
    p = _REPO_ROOT / EXAMPLE_PAYLOAD_PATH
    assert p.exists(), f"committed example missing: {EXAMPLE_PAYLOAD_PATH}"
    data = json.loads(p.read_text(encoding="utf-8"))
    for f in OPERATOR_EVENT_REQUIRED_FIELDS:
        assert f in data, f"example missing required field {f}"
        assert data[f] == EXAMPLE_OPERATOR_REGULATORY_EVENT_PAYLOAD[f]
    assert data["operator_confirmed"] is False
    assert data["live_approved"] is False
    # validate 가 example 을 reject(real event 아님).
    cv = validate_operator_regulatory_event_payload(data)
    assert cv["confirmation_valid"] is False
