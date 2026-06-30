"""ADR#90 — operator_confirmed_live_runner 테스트(load→§8 gate→live→분류; example/secret/PII/not-approved fail-closed)."""
from __future__ import annotations

import json

from backend.app.tools.operator_confirmed_live_runner import run_operator_confirmed_live
from backend.app.tools.operator_regulatory_event_payload import (
    EXAMPLE_OPERATOR_REGULATORY_EVENT_PAYLOAD,
)

# operator 확인·승인된 valid payload(epa seed — bank 의 regulatory_domain='agency final rule' allowed).
_VALID_APPROVED = {
    "seed_id": "epa_final_rule_emissions",
    "operator_confirmed": True,
    "confirmed_by": "ops_lead_unique_marker",   # PII-성 이름 — 출력에 새면 안 됨.
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


def _write(tmp_path, payload) -> str:
    p = tmp_path / "operator_payload.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def _fake_acq_factory():
    calls = []

    def fake_acq(seed, *, live_approved, today=None, **kw):
        calls.append({"seed": seed, "live_approved": live_approved})
        return {
            "official_news_live_status": "production_batch_frozen",
            "live_query_executed": True,
            "official_records_count": 3,
            "news_records_count": 2,
            "bridge_candidate_count": 2,
            "freeze_eligible_count": 1,
            "production_candidate_status": "frozen",
            "production_candidate_batch_ready": True,
            "production_frozen_pair_count": 1,
            "candidate_provenance": "live_official_news",
            "reviewer_handoff_ready": True,
            "production_gold_count": 0,
            "current_r1_gap": 200,
            "merge_allowed": False, "llm_invoked": False, "embedding_invoked": False, "db_write": False,
        }

    return fake_acq, calls


# ── 7. missing real payload → operator_payload_missing ─────────────────────────────────────────────────────
def test_07_missing_payload(tmp_path):
    out = run_operator_confirmed_live(str(tmp_path / "nope.json"))
    assert out["operator_payload_status"] == "not_provided"
    assert out["operator_event_status"] == "not_provided"
    assert out["live_query_executed"] is False
    assert out["live_no_yield_taxonomy_status"] == "missing_payload"


# ── 8. example payload cannot trigger live ─────────────────────────────────────────────────────────────────
def test_08_example_payload_cannot_trigger_live(tmp_path):
    path = _write(tmp_path, EXAMPLE_OPERATOR_REGULATORY_EVENT_PAYLOAD)
    out = run_operator_confirmed_live(path)
    assert out["payload_is_example_dummy"] is True
    assert out["live_query_executed"] is False
    assert out["live_no_yield_taxonomy_status"] == "operator_payload_example_detected"


# ── 10. invalid real payload (bad JSON) blocks live ────────────────────────────────────────────────────────
def test_10_invalid_json_blocks_live(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    out = run_operator_confirmed_live(str(p))
    assert out["operator_payload_status"] == "present_invalid_json"
    assert out["live_query_executed"] is False
    assert out["live_no_yield_taxonomy_status"] == "invalid_payload"


# ── 10b. invalid confirmation (placeholder) blocks live ────────────────────────────────────────────────────
def test_10b_placeholder_confirmation_blocks_live(tmp_path):
    bad = dict(_VALID_APPROVED, agency_or_entity="<Agency placeholder>")
    out = run_operator_confirmed_live(_write(tmp_path, bad))
    assert out["operator_event_status"] == "invalid_confirmation"
    assert out["live_query_executed"] is False
    assert out["live_no_yield_taxonomy_status"] == "invalid_payload"


# ── 11/12. secret/PII nested field blocks live (fail-closed·값 미노출) ──────────────────────────────────────
def test_11_secret_nested_field_blocks_live(tmp_path):
    secret_payload = dict(_VALID_APPROVED, nested={"api_key": "SECRET_VALUE_ZZZ"})
    out = run_operator_confirmed_live(_write(tmp_path, secret_payload))
    assert out["operator_payload_status"] == "present_rejected_pii_or_secret"
    assert out["live_query_executed"] is False
    assert out["live_no_yield_taxonomy_status"] == "payload_secret_or_pii_blocked"
    # secret 값은 출력 어디에도 없어야 한다.
    assert "SECRET_VALUE_ZZZ" not in json.dumps(out, default=str)


def test_12_pii_nested_field_blocks_live(tmp_path):
    pii_payload = dict(_VALID_APPROVED, contact={"reviewer_email": "person@example.com"})
    out = run_operator_confirmed_live(_write(tmp_path, pii_payload))
    assert out["operator_payload_status"] == "present_rejected_pii_or_secret"
    assert out["live_query_executed"] is False
    assert "person@example.com" not in json.dumps(out, default=str)


# ── 13. live_approved=false blocks live ────────────────────────────────────────────────────────────────────
def test_13_not_approved_blocks_live(tmp_path):
    not_approved = dict(_VALID_APPROVED, live_approved=False)
    out = run_operator_confirmed_live(_write(tmp_path, not_approved))
    assert out["operator_event_status"] == "confirmed_not_approved"
    assert out["live_query_executed"] is False
    assert out["live_no_yield_taxonomy_status"] == "payload_not_approved"


# ── 14. valid approved payload calls live engine ───────────────────────────────────────────────────────────
def test_14_valid_approved_calls_engine(tmp_path):
    fake_acq, calls = _fake_acq_factory()
    out = run_operator_confirmed_live(_write(tmp_path, _VALID_APPROVED), acquisition_fn=fake_acq)
    assert len(calls) == 1
    assert calls[0]["live_approved"] is True
    assert out["operator_event_status"] == "confirmed_live_executed"
    assert out["live_query_executed"] is True
    assert out["live_no_yield_taxonomy_status"] == "freeze_succeeded"
    assert out["official_records_count"] == 3
    assert out["bridge_candidate_count"] == 2
    assert out["reviewer_handoff_ready"] is True


# ── 15. valid approved payload → seed provenance=operator_confirmed_event ──────────────────────────────────
def test_15_seed_provenance_operator_confirmed(tmp_path):
    fake_acq, calls = _fake_acq_factory()
    out = run_operator_confirmed_live(_write(tmp_path, _VALID_APPROVED), acquisition_fn=fake_acq)
    assert out["seed_provenance"] == "operator_confirmed_event"
    # engine 에 전달된 seed 도 operator_confirmed_event provenance.
    assert calls[0]["seed"]["provenance"] == "operator_confirmed_event"
    assert calls[0]["seed"]["same_event_asserted"] is False


# ── 16. raw payload text not surfaced ──────────────────────────────────────────────────────────────────────
def test_16_raw_payload_not_surfaced(tmp_path):
    fake_acq, _ = _fake_acq_factory()
    out = run_operator_confirmed_live(_write(tmp_path, _VALID_APPROVED), acquisition_fn=fake_acq)
    dumped = json.dumps(out, default=str)
    # confirmed_by(PII-성 이름) 등 raw payload 본문은 출력에 재임베드되지 않는다.
    assert "ops_lead_unique_marker" not in dumped
    # gold/merge/sending 불변.
    assert out["production_gold_count"] == 0
    assert out["actual_sending_performed"] is False
    assert out["merge_allowed"] is False
    assert out["same_event_asserted"] is False


# ── reviewer_contact_checklist_ready = handoff ∧ dropbox (freeze 시에만) ────────────────────────────────────
def test_checklist_ready_only_with_freeze(tmp_path):
    # not_provided → handoff False → checklist not ready (dropbox 는 ready 가능).
    out_block = run_operator_confirmed_live(str(tmp_path / "nope.json"))
    assert out_block["reviewer_contact_checklist_ready"] is False
    # valid approved + freeze → handoff True → checklist ready.
    fake_acq, _ = _fake_acq_factory()
    out_live = run_operator_confirmed_live(_write(tmp_path, _VALID_APPROVED), acquisition_fn=fake_acq)
    assert out_live["reviewer_contact_checklist_ready"] == bool(out_live["label_dropbox_ready"])
    assert out_live["reviewer_contact_checklist_ready"] is True
