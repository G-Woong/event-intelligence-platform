"""ADR#95 §12/§21 — first_payload_candidate_evidence_binder 테스트(검증 대상 묶음·확정 0·payload 0·live 트리거 0·network 0).

검증(§21 #28-34): status=evidence_binder_ready, binder_is_confirmation/binder_is_payload False, official/news 검증
대상이 **분리**되고 둘 다 비어있지 않으며, official/news query 초안이 그 구조 안에 존재(truth 아님·draft), 미해결
질문·예상 실패 모드 비어있지 않음, live 트리거 불가 + network 0, same_event 단정 0·event_occurrence_verified 0·
production gold 0, `_assert_pii_safe` 통과, sanitized 투영에 status 존재.
"""
from __future__ import annotations

import inspect

from backend.app.tools.first_payload_candidate_evidence_binder import (
    BINDER_READY,
    CONTRACT_VERSION,
    DEFAULT_CANDIDATE_ID,
    OPERATION_NAME,
    build_first_payload_candidate_evidence_binder,
    main,
    sanitized_first_payload_candidate_evidence_binder,
)
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

_FORBIDDEN_KEYS = {"reviewer_name", "name", "email", "phone", "score", "model_score", "rationale",
                   "predicted_status", "raw_body", "body", "secret", "api_key", "provider_secret"}

_REQUIRED_KEYS = {
    "operation_name", "contract_version", "first_payload_evidence_binder_status", "candidate_summary",
    "official_evidence_to_verify", "news_evidence_to_verify", "date_window_to_verify", "agency_entity_to_verify",
    "action_phrase_to_verify", "canonical_url_to_verify", "published_at_to_verify", "source_role_notes",
    "expected_failure_modes", "next_query_adjustments", "unresolved_questions",
}


def _walk_keys(obj: object):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


# ── required keys + lead operation/contract/status (default → epa) ─────────────────────────────────────────────
def test_required_keys_and_status_ready():
    out = build_first_payload_candidate_evidence_binder()
    assert _REQUIRED_KEYS <= set(out)
    assert out["operation_name"] == OPERATION_NAME
    assert out["contract_version"] == CONTRACT_VERSION
    assert out["first_payload_evidence_binder_status"] == BINDER_READY
    assert out["candidate_id"] == DEFAULT_CANDIDATE_ID == "epa_final_rule_emissions"


# ── binder is NOT a confirmation ───────────────────────────────────────────────────────────────────────────────
def test_binder_is_not_confirmation():
    out = build_first_payload_candidate_evidence_binder()
    assert out["binder_is_confirmation"] is False
    assert out["binder_claims_event_occurred"] is False


# ── binder is NOT a payload ────────────────────────────────────────────────────────────────────────────────────
def test_binder_is_not_payload():
    out = build_first_payload_candidate_evidence_binder()
    assert out["binder_is_payload"] is False


# ── official_evidence_to_verify and news_evidence_to_verify are SEPARATE and non-empty ─────────────────────────
def test_official_and_news_evidence_separate_and_non_empty():
    out = build_first_payload_candidate_evidence_binder()
    official = out["official_evidence_to_verify"]
    news = out["news_evidence_to_verify"]
    assert isinstance(official, dict) and official
    assert isinstance(news, dict) and news
    # 분리: 같은 객체도, 같은 값도 아니다(official=evidence·news=reporting role 분리).
    assert official is not news
    assert official != news
    assert official["provider"] == "federal_register"
    assert "guardian" in news["providers"] and "nyt" in news["providers"]


# ── query DRAFTS present inside the to_verify structures (official & news query strings) ───────────────────────
def test_query_drafts_present_inside_structures():
    out = build_first_payload_candidate_evidence_binder()
    bank = build_regulatory_event_seed_bank()
    seed = next(s for s in bank["seed_bank"] if s["seed_id"] == DEFAULT_CANDIDATE_ID)
    official_draft = out["official_evidence_to_verify"]["official_query_draft"]
    news_draft = out["news_evidence_to_verify"]["news_query_draft"]
    assert isinstance(official_draft, str) and official_draft
    assert isinstance(news_draft, str) and news_draft
    # 초안은 seed bank(단일 출처)에서 온 값과 일치(하드코딩 0).
    assert official_draft == seed["official_query"]
    assert news_draft == seed["news_query"]
    assert "emissions" in official_draft.lower()
    assert "emissions" in news_draft.lower()
    # 초안은 truth 가 아니다.
    assert out["query_drafts_are_not_truth"] is True


# ── unresolved_questions is a non-empty list ───────────────────────────────────────────────────────────────────
def test_unresolved_questions_non_empty():
    out = build_first_payload_candidate_evidence_binder()
    q = out["unresolved_questions"]
    assert isinstance(q, list) and len(q) > 0


# ── expected_failure_modes is a non-empty list (carries seed.risk for title divergence) ────────────────────────
def test_expected_failure_modes_non_empty():
    out = build_first_payload_candidate_evidence_binder()
    modes = out["expected_failure_modes"]
    assert isinstance(modes, list) and len(modes) > 0
    mode_names = {m["mode"] for m in modes}
    assert {"official_out_of_window", "news_out_of_window", "no_entity_overlap"} <= mode_names


# ── binder cannot trigger live (no acquisition_fn param) AND network not invoked ───────────────────────────────
def test_binder_cannot_trigger_live_and_no_network():
    import backend.app.tools.first_payload_candidate_evidence_binder as mod

    out = build_first_payload_candidate_evidence_binder()
    assert out["binder_can_trigger_live"] is False
    assert out["network_invoked"] is False
    sig = inspect.signature(build_first_payload_candidate_evidence_binder)
    assert "acquisition_fn" not in sig.parameters
    # 모듈 소스가 live runner 를 import/호출하지 않고 network client 도 없다.
    with open(mod.__file__, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "operator_confirmed_live_runner" not in text
    assert "import httpx" not in text
    assert "import requests" not in text


# ── same_event is NOT asserted ─────────────────────────────────────────────────────────────────────────────────
def test_same_event_not_asserted():
    out = build_first_payload_candidate_evidence_binder()
    assert out["same_event_asserted"] is False


# ── event occurrence is NOT verified ───────────────────────────────────────────────────────────────────────────
def test_event_occurrence_not_verified():
    out = build_first_payload_candidate_evidence_binder()
    assert out["event_occurrence_verified"] is False
    assert "NOT" in out["candidate_summary"]


# ── production gold count is 0 (binder does not increment gold) ────────────────────────────────────────────────
def test_production_gold_count_zero():
    out = build_first_payload_candidate_evidence_binder()
    assert out["production_gold_count"] == 0


# ── _assert_pii_safe passes and no forbidden keys anywhere ─────────────────────────────────────────────────────
def test_pii_safe_passes():
    out = build_first_payload_candidate_evidence_binder()
    _assert_pii_safe(out, _path="first_payload_evidence_binder_output")  # raises on leak
    keys = set(_walk_keys(out))
    assert keys.isdisjoint(_FORBIDDEN_KEYS), keys & _FORBIDDEN_KEYS


# ── sanitized projection carries the status (and is a subset) ──────────────────────────────────────────────────
def test_sanitized_has_status():
    out = build_first_payload_candidate_evidence_binder()
    s = sanitized_first_payload_candidate_evidence_binder(out)
    assert "first_payload_evidence_binder_status" in s
    assert s["first_payload_evidence_binder_status"] == BINDER_READY
    assert set(s).issubset(set(out) | {
        "official_provider", "news_providers", "expected_failure_mode_count",
        "next_query_adjustment_count", "unresolved_question_count"})


# ── CLI --json smoke (exit 0 · status present · query draft excluded from aggregate) ───────────────────────────
def test_main_json_smoke(capsys):
    rc = main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "first_payload_evidence_binder_status" in captured.out
    assert "official_query_draft" not in captured.out
