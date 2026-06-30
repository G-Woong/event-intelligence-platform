"""ADR#90 — live_no_yield_taxonomy 테스트(세분 분류·각 항목 operator/engineer 양면 + next action·overlap finer 분류)."""
from __future__ import annotations

from backend.app.tools.live_no_yield_taxonomy import (
    TX_DATE_PROXIMITY_FAILED,
    TX_EXAMPLE_DETECTED,
    TX_FREEZE_SUCCEEDED,
    TX_FREEZE_UNSAFE,
    TX_INVALID_PAYLOAD,
    TX_MISSING_PAYLOAD,
    TX_NEWS_NO_RECORDS,
    TX_NO_ACTION_OVERLAP,
    TX_NO_ENTITY_OVERLAP,
    TX_NO_IN_WINDOW_NEWS,
    TX_NO_OVERLAP,
    TX_OFFICIAL_NO_RECORDS,
    TX_PAYLOAD_NOT_APPROVED,
    TX_PAYLOAD_SECRET_OR_PII,
    build_live_no_yield_taxonomy,
    classify_live_no_yield,
    classify_overlap_failure,
    taxonomy_entry,
)

_REQUIRED_FIELDS = (
    "operator_facing_explanation", "engineer_facing_cause", "next_action",
    "recommended_payload_adjustment", "recommended_source_adjustment",
)


def _acq(status: str) -> dict:
    return {"official_news_live_status": status}


# ── 24. official_no_records classified ─────────────────────────────────────────────────────────────────────
def test_24_official_no_records_classified():
    e = classify_live_no_yield(_acq("official_no_records"))
    assert e["taxonomy_key"] == TX_OFFICIAL_NO_RECORDS
    assert e["stage"] == "official"


# ── 25. news_no_records classified ─────────────────────────────────────────────────────────────────────────
def test_25_news_no_records_classified():
    e = classify_live_no_yield(_acq("news_no_records"))
    assert e["taxonomy_key"] == TX_NEWS_NO_RECORDS


# ── 26. no_in_window_news classified ───────────────────────────────────────────────────────────────────────
def test_26_no_in_window_news_classified():
    e = classify_live_no_yield(_acq("no_in_window_news"))
    assert e["taxonomy_key"] == TX_NO_IN_WINDOW_NEWS


# ── 27/28/29. overlap finer sub-cause(entity/action/date) ──────────────────────────────────────────────────
def test_27_no_entity_overlap_classified():
    e = classify_overlap_failure(entity_overlap=False, action_overlap=True, date_close=True)
    assert e["taxonomy_key"] == TX_NO_ENTITY_OVERLAP


def test_28_no_action_overlap_classified():
    e = classify_overlap_failure(entity_overlap=True, action_overlap=False, date_close=True)
    assert e["taxonomy_key"] == TX_NO_ACTION_OVERLAP


def test_29_date_proximity_failed_classified():
    e = classify_overlap_failure(entity_overlap=True, action_overlap=True, date_close=False)
    assert e["taxonomy_key"] == TX_DATE_PROXIMITY_FAILED


def test_29b_overlap_present_is_not_no_yield():
    e = classify_overlap_failure(entity_overlap=True, action_overlap=True, date_close=True)
    assert e["taxonomy_key"] == TX_FREEZE_SUCCEEDED  # overlap 성립 → no-yield 아님.


# ── 30. freeze_unsafe classified ───────────────────────────────────────────────────────────────────────────
def test_30_freeze_unsafe_classified():
    e = classify_live_no_yield(_acq("official_news_bridge_candidates_found"))
    assert e["taxonomy_key"] == TX_FREEZE_UNSAFE
    assert e["is_yield"] is False


# ── taxonomy 키 카운트 락(adversarial F1 — 문서 "21-key" 와 코드 정합·조용한 드리프트 차단) ──────────────────
def test_taxonomy_key_count_locked_at_21():
    out = build_live_no_yield_taxonomy()
    # 21 = no-yield 원인 20 + freeze_succeeded 1(yield). 키 추가/삭제 시 이 락이 문서와 함께 깨진다.
    assert out["taxonomy_key_count"] == 21
    assert len(out["taxonomy_registry"]) == 21


# ── 31. each taxonomy has operator-facing explanation ──────────────────────────────────────────────────────
def test_31_each_has_operator_facing_explanation():
    reg = build_live_no_yield_taxonomy()["taxonomy_registry"]
    assert len(reg) >= 13
    for k, e in reg.items():
        assert e["operator_facing_explanation"].strip(), k


# ── 32. each taxonomy has next_action(+ 모든 5필드) ────────────────────────────────────────────────────────
def test_32_each_has_all_five_fields():
    reg = build_live_no_yield_taxonomy()["taxonomy_registry"]
    for k, e in reg.items():
        for f in _REQUIRED_FIELDS:
            assert isinstance(e.get(f), str) and e[f].strip(), f"{k}.{f}"


# ── payload-stage 우선(missing/invalid/secret-PII/not-approved) ────────────────────────────────────────────
def test_payload_missing_takes_precedence():
    e = classify_live_no_yield(_acq("official_no_records"),
                               payload_entrypoint_out={"operator_payload_status": "not_provided"})
    assert e["taxonomy_key"] == TX_MISSING_PAYLOAD  # engine status 무시하고 payload-stage 우선.


def test_payload_invalid_classified():
    e = classify_live_no_yield(None, payload_entrypoint_out={"operator_payload_status": "present_invalid_json"})
    assert e["taxonomy_key"] == TX_INVALID_PAYLOAD


def test_payload_secret_or_pii_classified():
    e = classify_live_no_yield(None,
                               payload_entrypoint_out={"operator_payload_status": "present_rejected_pii_or_secret"})
    assert e["taxonomy_key"] == TX_PAYLOAD_SECRET_OR_PII


def test_payload_not_approved_classified():
    e = classify_live_no_yield(_acq("blocked_no_live_opt_in"))
    assert e["taxonomy_key"] == TX_PAYLOAD_NOT_APPROVED


def test_example_dummy_in_real_path_detected():
    # real 경로에 example dummy(valid JSON 이지만 real event 아님) → example-detected 우선.
    e = classify_live_no_yield(
        _acq("blocked_operator_not_confirmed"),
        payload_entrypoint_out={"operator_payload_status": "present_valid_json", "payload_is_example_dummy": True})
    assert e["taxonomy_key"] == TX_EXAMPLE_DETECTED


def test_intake_blocked_operator_not_confirmed_maps_to_invalid():
    # present_valid 이지만 operator_confirmed=false → intake blocked status → invalid_payload.
    e = classify_live_no_yield(
        _acq("blocked_operator_not_confirmed"),
        payload_entrypoint_out={"operator_payload_status": "present_valid_json"})
    assert e["taxonomy_key"] == TX_INVALID_PAYLOAD


# ── freeze_succeeded → is_yield True ───────────────────────────────────────────────────────────────────────
def test_freeze_succeeded_is_yield():
    out = build_live_no_yield_taxonomy(_acq("production_batch_frozen"))
    assert out["live_no_yield_taxonomy_status"] == TX_FREEZE_SUCCEEDED
    assert out["is_yield"] is True


# ── no acquisition + no payload → not_run(fail-closed) ─────────────────────────────────────────────────────
def test_not_run_when_no_input():
    out = build_live_no_yield_taxonomy()
    assert out["live_no_yield_taxonomy_status"] == "not_run"
    assert out["is_yield"] is False


# ── umbrella overlap → sub-cause 후보 노출(과대단정 0) ─────────────────────────────────────────────────────
def test_overlap_umbrella_exposes_sub_cause_candidates():
    e = classify_live_no_yield(_acq("no_official_news_overlap"))
    assert e["taxonomy_key"] == TX_NO_OVERLAP
    assert set(e["candidate_sub_causes"]) == {
        TX_NO_ENTITY_OVERLAP, TX_NO_ACTION_OVERLAP, TX_DATE_PROXIMITY_FAILED}


# ── registry entry 직접 조회 fail-closed ───────────────────────────────────────────────────────────────────
def test_unknown_key_fails_closed_to_not_run():
    e = taxonomy_entry("does_not_exist")
    assert e["taxonomy_key"] == "not_run"
