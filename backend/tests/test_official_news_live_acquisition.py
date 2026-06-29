"""ADR#87 — official×news live acquisition tests(§19 tests 14~27·42~48·freeze 통합·merge 0·gold 0·전송 0).

정책을 테스트로 잠근다: seed 검증·opt-in 게이트·official(FR)+news(guardian) fetch·enforce_window·bridge·freeze
(publishable×publishable·gold 0)·handoff·official×news 전용 instruction·blocked reason 정직 분해·invariant.
fake transport 로 결정론(network 0·key 불요)."""
from __future__ import annotations

import json

from backend.app.tools.official_news_live_acquisition import (
    ONL_BLOCKED_NO_OPT_IN,
    ONL_INVALID_SEED,
    ONL_NO_IN_WINDOW_NEWS,
    ONL_NO_OVERLAP,
    ONL_OFFICIAL_NO_RECORDS,
    ONL_PRODUCTION_BATCH_FROZEN,
    ONL_PROVIDER_UNAVAILABLE,
    build_official_news_reviewer_instruction,
    run_official_news_live_acquisition,
    sanitized_official_news_acquisition,
)

_WINDOW = ("2026-06-25", "2026-06-26")


def _seed(**over) -> dict:
    base = {
        "seed_id": "epa_test", "regulatory_domain": "agency final rule",
        "official_provider": "federal_register", "news_providers": ["guardian"],
        "agency": "Environmental Protection Agency", "entity": "EPA vehicle emissions standard",
        "action_phrase": "final rule on greenhouse gas emissions standards", "document_type": "Rule",
        "official_query": "EPA greenhouse gas emissions final rule", "news_query": "EPA emissions rule",
        "date_window_start": "2026-06-25", "date_window_end": "2026-06-26",
    }
    base.update(over)
    return base


def _env_present(keys):
    return {k: "present" for k in keys}


def _env_missing(keys):
    return {k: "missing" for k in keys}


def _fr_tx(*, count=1, pub="2026-06-25",
           title="Final Rule: Greenhouse Gas Emissions Standards for Vehicles"):
    def tx(url):
        if count == 0:
            return json.dumps({"count": 0, "description": "no documents"})
        return json.dumps({"count": count, "results": [{
            "title": title, "html_url": "https://www.federalregister.gov/documents/2026/06/25/epa",
            "publication_date": pub, "document_number": "2026-12345"}]})
    return tx


def _guardian_tx(*, pub="2026-06-26",
                 title="EPA finalises greenhouse gas emissions rule for vehicles"):
    def tx(url):
        return json.dumps({"response": {"status": "ok", "results": [{
            "webTitle": title,
            "webUrl": "https://www.theguardian.com/environment/2026/jun/26/epa-emissions",
            "webPublicationDate": pub}]}})
    return tx


# ── freeze chain fakes(run_r1_production_candidate_acquisition 결정론) ───────────────────────────────────────
def _fake_gate(**over) -> dict:
    base = {
        "operation_name": "reviewer_actual_input_gate", "batch_id": "b", "packet_id": "p",
        "input_directory": "outputs/reviewer_batch/b/intake", "input_directory_exists": False,
        "actual_contact_evidence_found": False, "actual_returned_labels_found": False,
        "contact_evidence_files": [], "returned_label_files": [],
        "actual_input_status": "no_actual_input", "external_input_required": True,
        "returned_label_count": 0, "missing_label_count": 0, "invalid_label_count": 0,
        "conflict_pair_count": 0, "calibration_gap": None, "calibration_delta": None,
        "production_gold_count": 0, "synthetic_gold_count": 0,
        "calibration_ready": False, "merge_gate_ready": False,
        "public_truth_exposed": False, "same_event_truth_exposed": False, "raw_pii_exposed": False,
        "score_exposed": False, "rationale_exposed": False, "predicted_status_exposed": False,
        "actual_sending_performed": False, "no_public_intelligence_unit": True,
        "merge_allowed": False, "no_merge_without_gold": True,
        "db_write": False, "llm_invoked": False, "embedding_invoked": False,
        "block_reasons": [], "next_actions": [],
    }
    base.update(over)
    return base


def _gate_fn(**over):
    return lambda **kw: _fake_gate(**over)


def _readiness_fn(ready: bool = True):
    return lambda: {"credential_status": {"guardian": ready, "nyt": ready}}


def _synth_fn():
    return lambda **kw: {"batch_id": "synth_001", "batch_frozen": True,
                         "frozen_pair_count": 5, "pilot_batch_is_production_candidate": False}


def _run_frozen(**over):
    """freeze 까지 도는 결정론 실행(FR+guardian in-window 공유 토큰·실 freeze 머신)."""
    kw = dict(
        seed=_seed(), live_approved=True, env_status_fn=_env_present,
        transport_fr=_fr_tx(), transport_news={"guardian": _guardian_tx()},
        gate_fn=_gate_fn(), readiness_fn=_readiness_fn(), synthetic_batch_fn=_synth_fn())
    kw.update(over)
    return run_official_news_live_acquisition(**kw)


# ── §19 test 15: invalid seed blocks live ───────────────────────────────────────────────────────────────
def test_15_invalid_seed_blocks_live():
    out = run_official_news_live_acquisition(_seed(date_window_start="", date_window_end=""), live_approved=True)
    assert out["official_news_live_status"] == ONL_INVALID_SEED
    assert out["live_query_executed"] is False
    assert out["blocked_reason"] == ONL_INVALID_SEED
    assert "missing_date_window" in out["regulatory_seed_rejection_reasons"]


# ── §19 test 14: no approval blocks live ────────────────────────────────────────────────────────────────
def test_14_no_approval_blocks_live():
    out = run_official_news_live_acquisition(_seed(), live_approved=False)
    assert out["official_news_live_status"] == ONL_BLOCKED_NO_OPT_IN
    assert out["live_query_executed"] is False
    assert out["live_call_count"] == 0


# ── §19 test 17: news provider unavailable classified ───────────────────────────────────────────────────
def test_17_news_provider_unavailable():
    # guardian credential missing → news fetch 차단 → provider_unavailable(FR key-free 라 무관).
    out = run_official_news_live_acquisition(
        _seed(), live_approved=True, env_status_fn=_env_missing,
        transport_fr=_fr_tx(), transport_news={"guardian": _guardian_tx()})
    assert out["official_news_live_status"] == ONL_PROVIDER_UNAVAILABLE
    assert out["news_provider_status"]["guardian"] == "missing_credentials"


# ── code-review NIT-1: FR host-gate 차단이 rate-limit 로 오분류되지 않음(host-gate 먼저 분류) ────────────────
class _BlockingGate:
    """모든 host 호출을 차단하는 fake host gate(decide.allowed=False). run_provider_query 가 fetch 전 host_gate_blocked."""
    def decide(self, key, *, min_spacing_seconds=0):
        class _D:
            allowed = False
            reason = "host_min_spacing_not_elapsed"
        return _D()

    def record_call(self, key):
        pass


def test_18_fr_host_gate_classified_as_host_gate_not_rate():
    # FR 이 host-floor 로 차단되면(federal_register_live_smoke 가 fr_live_rate_blocked 로 collapse 해도)
    # blocked_host_gate 로 분류돼야 함(rate-limit 오분류 금지·올바른 next_action).
    out = run_official_news_live_acquisition(
        _seed(), live_approved=True, env_status_fn=_env_present,
        transport_fr=_fr_tx(), transport_news={"guardian": _guardian_tx()}, host_gate=_BlockingGate())
    assert out["official_news_live_status"] == "blocked_host_gate"
    assert "host floor" in out["next_action"].lower()


# ── §19 test 23: official_no_records classified ─────────────────────────────────────────────────────────
def test_23_official_no_records():
    out = run_official_news_live_acquisition(
        _seed(), live_approved=True, env_status_fn=_env_present,
        transport_fr=_fr_tx(count=0), transport_news={"guardian": _guardian_tx()})
    assert out["official_news_live_status"] == ONL_OFFICIAL_NO_RECORDS
    assert out["official_records_count"] == 0


# ── §19 test 25: no_in_window_news classified(enforce_window 강제) ──────────────────────────────────────
def test_25_no_in_window_news():
    # guardian 가 window 밖(6/29) 기사 반환 → enforce_window 가 drop → no_in_window_news.
    out = run_official_news_live_acquisition(
        _seed(), live_approved=True, env_status_fn=_env_present,
        transport_fr=_fr_tx(), transport_news={"guardian": _guardian_tx(pub="2026-06-29")})
    assert out["official_news_live_status"] == ONL_NO_IN_WINDOW_NEWS
    assert out["news_records_count"] == 0


# ── §19 test 26: no_official_news_overlap classified(domain mismatch) ───────────────────────────────────
def test_26_no_official_news_overlap():
    # FR(emissions rule) vs guardian(무관 stock 기사) → 공유 토큰 < 2 → no overlap.
    out = run_official_news_live_acquisition(
        _seed(), live_approved=True, env_status_fn=_env_present,
        transport_fr=_fr_tx(), transport_news={"guardian": _guardian_tx(
            title="Stock markets rally on technology earnings results")})
    assert out["official_news_live_status"] == ONL_NO_OVERLAP
    assert out["official_records_count"] == 1 and out["news_records_count"] == 1
    assert out["bridge_candidate_count"] == 0


# ── §19 test 27 + 44/45: bridge candidates found → freeze → reviewer worklist(gold 0) ───────────────────
def test_27_bridge_candidates_found_and_frozen():
    out = _run_frozen()
    assert out["official_news_live_status"] == ONL_PRODUCTION_BATCH_FROZEN
    assert out["bridge_candidate_count"] == 1 and out["freeze_eligible_count"] == 1
    assert out["production_candidate_batch_ready"] is True
    assert out["production_frozen_pair_count"] == 1
    assert out["candidate_provenance"] == "live_derived"
    # §11 freeze success: handoff ready·gold 0.
    assert out["reviewer_handoff_ready"] is True
    assert out["production_gold_count"] == 0


# ── §19 test 46: freeze does not expose score/rationale/predicted/raw/PII ────────────────────────────────
def test_46_freeze_no_forbidden_exposure():
    out = _run_frozen()
    for k in ("score_exposed", "rationale_exposed", "predicted_status_exposed", "raw_pii_exposed",
              "raw_source_body_exposed", "same_event_truth_exposed", "bridge_score_exposed"):
        assert out[k] is False
    blob = json.dumps(out, ensure_ascii=False, default=str)
    for forbidden in ('"score":', '"rationale":', '"predicted_status":', '"raw_body":', '"api_key":'):
        assert forbidden not in blob


# ── §19 test 48 + 72/74/75/76: invariants(전송 0·merge 0·gold 0·LLM 0·DB 0) ─────────────────────────────
def test_48_freeze_invariants():
    out = _run_frozen()
    assert out["actual_sending_performed"] is False
    assert out["merge_allowed"] is False
    assert out["db_write"] is False
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False
    assert out["same_event_asserted"] is False
    assert out["official_alone_as_production_candidate"] is False
    assert out["official_news_role_separated"] is True
    assert out["r2_r7_no_go"] is True


# ── §19 test 42: no bridge candidate → no freeze ────────────────────────────────────────────────────────
def test_42_no_candidate_no_freeze():
    out = run_official_news_live_acquisition(
        _seed(), live_approved=True, env_status_fn=_env_present,
        transport_fr=_fr_tx(), transport_news={"guardian": _guardian_tx(
            title="Stock markets rally on technology earnings results")},
        gate_fn=_gate_fn(), readiness_fn=_readiness_fn(), synthetic_batch_fn=_synth_fn())
    assert out["production_candidate_batch_ready"] is False
    assert out["reviewer_handoff_ready"] is False
    assert out["production_frozen_pair_count"] == 0


# ── §19 test 49~53: official×news reviewer instruction(official=evidence·news=reporting·distinct) ────────
def test_49_official_news_reviewer_instruction():
    instr = build_official_news_reviewer_instruction()
    assert "authoritative evidence" in instr["official_source_role"].lower()
    assert "reporting" in instr["news_source_role"].lower()
    assert "same real-world regulatory event" in instr["purpose"].lower()
    # label vocabulary 는 news×news 와 동일 단일 출처(4-label).
    assert set(instr["label_vocabulary"]) == {"same_event", "different_event", "unsure", "needs_review"}
    # §12 must not include — score/rationale/predicted/same_event truth.
    assert instr["model_score_shown"] is False and instr["model_rationale_shown"] is False
    assert instr["predicted_status_shown"] is False and instr["same_event_truth_asserted"] is False


def test_50_frozen_run_surfaces_official_news_instruction():
    out = _run_frozen()
    assert out["official_news_label_instruction_ready"] is True
    assert out["official_news_label_instruction"]["purpose"]
    assert out["expected_label_files_ready"] is True
    assert out["validation_command_ready"] is True
    assert out["placement_guide_ready"] is True


# ── §19 test 58~71: sanitized projection(aggregate-only·title/url/instruction 본문 제외) ──────────────────
def test_sanitized_projection_no_titles_or_urls():
    out = _run_frozen()
    agg = sanitized_official_news_acquisition(out)
    assert agg["official_news_live_status"] == ONL_PRODUCTION_BATCH_FROZEN
    assert agg["bridge_candidate_count"] == 1
    blob = json.dumps(agg, ensure_ascii=False)
    # title/url/instruction 본문 미노출(aggregate count/status 만).
    for leak in ("Final Rule", "theguardian.com", "federalregister.gov", "greenhouse"):
        assert leak not in blob


def test_seed_validity_surfaced():
    out = _run_frozen()
    assert out["regulatory_seed_valid"] is True
    assert out["selected_regulatory_seed_id"] == "epa_test"
    assert out["official_provider_used"] == "federal_register"
    assert out["news_providers_used"] == ["guardian"]
