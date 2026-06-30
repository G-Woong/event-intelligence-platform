"""ADR#88 — operator_regulatory_event_intake tests (§19 6~17 + gate behavior · network 0 · merge 0)."""
from __future__ import annotations

from backend.app.tools.operator_regulatory_event_intake import (
    ONL_BLOCKED_INVALID_CONFIRMATION,
    ONL_BLOCKED_NO_OPT_IN,
    ONL_BLOCKED_OPERATOR_NOT_CONFIRMED,
    OPERATOR_EVENT_CONFIRMED_LIVE,
    OPERATOR_EVENT_CONFIRMED_NOT_APPROVED,
    OPERATOR_EVENT_INVALID_CONFIRMATION,
    OPERATOR_EVENT_NOT_CONFIRMED,
    OPERATOR_EVENT_NOT_PROVIDED,
    PROVENANCE_CODE_PROPOSED,
    PROVENANCE_OPERATOR_CONFIRMED,
    build_confirmed_seed_from_event,
    run_operator_regulatory_event_intake,
    sanitized_operator_intake,
    validate_operator_confirmed_event,
)


def _valid_payload(**overrides) -> dict:
    """§8 valid operator-confirmed event(EPA final rule·bank seed_id 와 동일·shape 통과). live_approved 기본 False."""
    payload = {
        "seed_id": "epa_final_rule_emissions",
        "operator_confirmed": True,
        "confirmed_by": "ops_lead",
        "confirmed_at": "2026-06-29",
        "agency_or_entity": "Environmental Protection Agency",
        "action_phrase": "final rule on greenhouse gas emissions standards",
        "date_window_start": "2026-06-25",
        "date_window_end": "2026-06-26",
        "official_query": "Environmental Protection Agency greenhouse gas emissions final rule",
        "news_query": "EPA emissions rule",
        "expected_news_angle": "news covers industry/political reaction to the EPA final rule",
        "live_approved": False,
    }
    payload.update(overrides)
    return payload


def _fake_acq(record: dict):
    """engine 대역 — 호출 인자 캡처 + frozen-batch-like 결과 반환(passthrough 검증용)."""
    def _fn(seed, *, live_approved, today=None, **kwargs):
        record["called"] = True
        record["seed"] = seed
        record["live_approved"] = live_approved
        return {
            "official_news_live_status": "production_batch_frozen",
            "official_records_count": 2,
            "news_records_count": 3,
            "bridge_candidate_count": 1,
            "freeze_eligible_count": 1,
            "production_candidate_status": "production_batch_frozen",
            "production_candidate_batch_ready": True,
            "production_frozen_pair_count": 1,
            "candidate_provenance": "live_derived",
            "reviewer_handoff_ready": True,
            "production_gold_count": 0,
            "current_r1_gap": 200,
            "merge_allowed": False,
            "llm_invoked": False,
            "embedding_invoked": False,
            "db_write": False,
        }
    return _fn


# ── §19-6: operator_confirmed=false blocks live ─────────────────────────────────────────────────────────
def test_06_operator_not_confirmed_blocks_live():
    rec: dict = {}
    out = run_operator_regulatory_event_intake(
        _valid_payload(operator_confirmed=False, live_approved=True), acquisition_fn=_fake_acq(rec))
    assert out["operator_event_status"] == OPERATOR_EVENT_NOT_CONFIRMED
    assert out["official_news_live_status"] == ONL_BLOCKED_OPERATOR_NOT_CONFIRMED
    assert out["live_allowed"] is False
    assert rec.get("called") is not True   # engine 미호출.


# ── §19-7: missing confirmed_by rejected ────────────────────────────────────────────────────────────────
def test_07_missing_confirmed_by_rejected():
    cv = validate_operator_confirmed_event(_valid_payload(confirmed_by=""))
    assert cv["confirmation_valid"] is False
    assert "missing_confirmed_by" in cv["rejection_reasons"]


# ── §19-8: invalid confirmed_at rejected ────────────────────────────────────────────────────────────────
def test_08_invalid_confirmed_at_rejected():
    cv = validate_operator_confirmed_event(_valid_payload(confirmed_at="June 29 2026"))
    assert cv["confirmation_valid"] is False
    assert "confirmed_at_not_iso" in cv["rejection_reasons"]
    # ISO datetime 은 허용.
    assert validate_operator_confirmed_event(
        _valid_payload(confirmed_at="2026-06-29T12:00:00+00:00"))["confirmation_valid"] is True


# ── §19-9: placeholder agency rejected ──────────────────────────────────────────────────────────────────
def test_09_placeholder_agency_rejected():
    cv = validate_operator_confirmed_event(_valid_payload(agency_or_entity="SEC enforcement (operator fills)"))
    assert cv["confirmation_valid"] is False
    assert "placeholder_agency_or_entity" in cv["rejection_reasons"]
    cv2 = validate_operator_confirmed_event(_valid_payload(agency_or_entity="<Agency>"))
    assert "placeholder_agency_or_entity" in cv2["rejection_reasons"]


# ── §19-10: generic action rejected ─────────────────────────────────────────────────────────────────────
def test_10_generic_action_rejected():
    for bad in ("enforcement", "action", "regulatory action", "rulemaking"):
        cv = validate_operator_confirmed_event(_valid_payload(action_phrase=bad))
        assert cv["confirmation_valid"] is False, bad
        assert "generic_action_phrase" in cv["rejection_reasons"], bad


# ── §19-11: missing date window rejected ────────────────────────────────────────────────────────────────
def test_11_missing_date_window_rejected():
    cv = validate_operator_confirmed_event(_valid_payload(date_window_start="", date_window_end=""))
    assert cv["confirmation_valid"] is False
    assert "missing_date_window" in cv["rejection_reasons"]
    # 비-ISO·역순도 reject.
    assert "date_window_not_iso" in validate_operator_confirmed_event(
        _valid_payload(date_window_start="2026/06/25"))["rejection_reasons"]
    assert "date_window_start_after_end" in validate_operator_confirmed_event(
        _valid_payload(date_window_start="2026-06-27", date_window_end="2026-06-26"))["rejection_reasons"]


# ── §19-12: broad topic rejected ────────────────────────────────────────────────────────────────────────
def test_12_broad_topic_rejected():
    cv = validate_operator_confirmed_event(
        _valid_payload(agency_or_entity="immigration", action_phrase="immigration",
                       official_query="immigration", news_query="immigration"))
    assert cv["confirmation_valid"] is False
    assert any(r.startswith("generic_") or r.startswith("broad_") for r in cv["rejection_reasons"])


# ── §19-13: same_event assertion rejected ───────────────────────────────────────────────────────────────
def test_13_operator_same_event_assertion_rejected():
    cv = validate_operator_confirmed_event(_valid_payload(same_event_asserted=True))
    assert cv["confirmation_valid"] is False
    assert "operator_asserted_same_event" in cv["rejection_reasons"]
    assert "operator_asserted_same_event" in validate_operator_confirmed_event(
        _valid_payload(same_event=True))["rejection_reasons"]


# ── §19-14: live_approved missing rejected ──────────────────────────────────────────────────────────────
def test_14_live_approved_missing_rejected():
    p = _valid_payload()
    del p["live_approved"]
    cv = validate_operator_confirmed_event(p)
    assert cv["confirmation_valid"] is False
    assert "missing_live_approved" in cv["rejection_reasons"]


# ── §19-15: valid operator confirmation accepted ────────────────────────────────────────────────────────
def test_15_valid_confirmation_accepted():
    cv = validate_operator_confirmed_event(_valid_payload(live_approved=True))
    assert cv["confirmation_valid"] is True
    assert cv["operator_confirmed"] is True
    assert cv["live_allowed"] is True
    assert cv["rejection_reasons"] == []
    # 확인은 truth 가 아님.
    assert cv["same_event_asserted"] is False
    assert cv["event_occurrence_verified_by_code"] is False


# ── §19-16: code_proposed seed not treated as confirmed ─────────────────────────────────────────────────
def test_16_code_proposed_not_treated_as_confirmed():
    # payload 없음(이번 턴 기본) — code_proposed seed bank 가 있어도 confirmed 로 둔갑하지 않는다.
    out = run_operator_regulatory_event_intake(None)
    assert out["operator_event_status"] == OPERATOR_EVENT_NOT_PROVIDED
    assert out["operator_confirmed"] is False
    assert out["seed_provenance"] == PROVENANCE_CODE_PROPOSED
    assert out["code_proposed_treated_as_confirmed"] is False
    assert out["official_news_live_status"] == ONL_BLOCKED_OPERATOR_NOT_CONFIRMED
    assert out["live_query_executed"] is False   # payload None → engine 미호출(raw acq 재임베드 0·NIT-1).


# ── §19-17: confirmation provenance recorded ────────────────────────────────────────────────────────────
def test_17_confirmation_provenance_recorded():
    cv = validate_operator_confirmed_event(_valid_payload(live_approved=True))
    assert cv["seed_provenance"] == PROVENANCE_OPERATOR_CONFIRMED
    seed = build_confirmed_seed_from_event(_valid_payload(live_approved=True))
    assert seed["provenance"] == PROVENANCE_OPERATOR_CONFIRMED
    assert seed["operator_confirmed"] is True
    assert seed["confirmed_by"] == "ops_lead"
    assert seed["event_occurrence_verified"] is False   # 확인 ≠ 발생 검증.
    assert seed["same_event_asserted"] is False


# ── gate behavior: confirmed + approved → engine 호출(operator-confirmed seed·live_approved=True) ─────────
def test_18_confirmed_and_approved_calls_engine():
    rec: dict = {}
    out = run_operator_regulatory_event_intake(
        _valid_payload(live_approved=True), acquisition_fn=_fake_acq(rec))
    assert rec["called"] is True
    assert rec["live_approved"] is True
    assert rec["seed"]["provenance"] == PROVENANCE_OPERATOR_CONFIRMED   # operator-confirmed seed 전달.
    assert out["operator_event_status"] == OPERATOR_EVENT_CONFIRMED_LIVE
    assert out["official_news_live_status"] == "production_batch_frozen"
    # engine aggregate passthrough.
    assert out["production_frozen_pair_count"] == 1
    assert out["reviewer_handoff_ready"] is True
    assert out["production_gold_count"] == 0           # freeze ≠ gold.
    assert out["blocked_reason"] == ""


# ── gate behavior: confirmed but not approved → blocked_no_live_opt_in(engine 미호출) ───────────────────
def test_19_confirmed_not_approved_blocks_without_engine_call():
    rec: dict = {}
    out = run_operator_regulatory_event_intake(
        _valid_payload(live_approved=False), acquisition_fn=_fake_acq(rec))
    assert out["operator_event_status"] == OPERATOR_EVENT_CONFIRMED_NOT_APPROVED
    assert out["official_news_live_status"] == ONL_BLOCKED_NO_OPT_IN
    assert out["live_allowed"] is False
    assert rec.get("called") is not True


# ── gate behavior: invalid confirmation → blocked_invalid_confirmation(engine 미호출) ───────────────────
def test_20_invalid_confirmation_blocks_without_engine_call():
    rec: dict = {}
    out = run_operator_regulatory_event_intake(
        _valid_payload(action_phrase="enforcement", live_approved=True), acquisition_fn=_fake_acq(rec))
    assert out["operator_event_status"] == OPERATOR_EVENT_INVALID_CONFIRMATION
    assert out["official_news_live_status"] == ONL_BLOCKED_INVALID_CONFIRMATION
    assert rec.get("called") is not True


# ── shape cross-check: unknown seed_id without regulatory_domain → invalid(shape) ───────────────────────
def test_21_unknown_seed_without_domain_invalid_shape():
    rec: dict = {}
    out = run_operator_regulatory_event_intake(
        _valid_payload(seed_id="unknown_seed_xyz", live_approved=True), acquisition_fn=_fake_acq(rec))
    # bank_seed 미발견 → regulatory_domain "" → validate_regulatory_seed shape reject.
    assert out["operator_event_status"] == OPERATOR_EVENT_INVALID_CONFIRMATION
    assert "shape:" in out["confirmation_blocked_reason"]
    assert rec.get("called") is not True
    # 단, payload 가 regulatory_domain 직접 제공하면 통과(operator fully-specified event).
    out2 = run_operator_regulatory_event_intake(
        _valid_payload(seed_id="operator_new_event", regulatory_domain="agency final rule", live_approved=True),
        acquisition_fn=_fake_acq({}))
    assert out2["operator_event_status"] == OPERATOR_EVENT_CONFIRMED_LIVE


# ── invariants: gold 0 · merge 0 · sending 0 · sanitized projection ─────────────────────────────────────
def test_22_invariants_and_sanitized_projection():
    out = run_operator_regulatory_event_intake(
        _valid_payload(live_approved=True), acquisition_fn=_fake_acq({}))
    assert out["production_gold_count"] == 0
    assert out["merge_allowed"] is False
    assert out["actual_sending_performed"] is False
    assert out["same_event_asserted"] is False
    assert out["operator_confirmation_as_same_event_truth"] is False
    assert out["r2_r7_no_go"] is True
    # raw engine 결과(acq)는 out 에 재임베드되지 않는다(title/canonical_url 누출 방어·adversarial NIT-1).
    assert "official_news_acquisition_result" not in out
    agg = sanitized_operator_intake(out)
    # aggregate projection 은 acq 전체/payload 본문을 포함하지 않는다.
    assert "official_news_acquisition_result" not in agg
    assert agg["operator_event_status"] == OPERATOR_EVENT_CONFIRMED_LIVE
    assert agg["seed_provenance"] == PROVENANCE_OPERATOR_CONFIRMED
