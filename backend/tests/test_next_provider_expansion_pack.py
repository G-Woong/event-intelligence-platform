"""ADR#93 §20 #57-#62 — next provider expansion pack tests.

검증: news_no_records→news breadth(GDELT 카드)·no_in_window_news→provider/date·official_no_records→official-side
먼저(news 비난 0)·GDELT attribution/rate risk high·runtime_enabled False·GDELT 실행 0·source role guard 보존·
friendly token "freeze_unsafe"→TX_FREEZE_UNSAFE→overlap refine·KO lane 분리·network 0·secret 값 0.
"""
from __future__ import annotations

from backend.app.tools.live_no_yield_taxonomy import TX_FREEZE_UNSAFE
from backend.app.tools.next_provider_expansion_pack import (
    NPE_NEWS_BREADTH,
    NPE_NOT_TRIGGERED,
    NPE_OFFICIAL_FIRST,
    NPE_OVERLAP_REFINE,
    NPE_PROVIDER_DATE,
    OPERATION_NAME,
    build_next_provider_expansion_pack,
    sanitized_next_provider_expansion_pack,
)


def _card(out: dict, sid: str):
    return next((c for c in out["provider_cards"] if c["source_id"] == sid), None)


# ── 57. news_no_records -> recommend news breadth provider (GDELT in cards) ──
def test_news_no_records_recommends_provider_expansion():
    out = build_next_provider_expansion_pack(
        no_yield_reason="news_no_records", official_records_count=3, news_records_count=0)
    assert out["next_provider_expansion_status"] == NPE_NEWS_BREADTH
    assert _card(out, "gdelt") is not None
    # AP/Reuters-like alternative also surfaced as a card.
    assert _card(out, "ap_reuters_like") is not None
    assert out["recommended_provider"] == "gdelt"


# ── 58. no_in_window_news -> recommend provider/date strategy ──
def test_no_in_window_news_recommends_provider_date():
    out = build_next_provider_expansion_pack(
        no_yield_reason="no_in_window_news", news_records_count=5, in_window_news_count=0)
    assert out["next_provider_expansion_status"] == NPE_PROVIDER_DATE
    assert out["recommended_provider"] == "federal_register"
    assert "window" in out["why_recommended"].lower()


# ── 59. official_no_records -> does NOT blame news first (official side) ──
def test_official_no_records_does_not_blame_news_first():
    out = build_next_provider_expansion_pack(
        no_yield_reason="official_no_records", official_records_count=0, news_records_count=5)
    assert out["next_provider_expansion_status"] == NPE_OFFICIAL_FIRST
    # recommendation targets the official side, not a news provider.
    assert out["source_role"] == "official"
    assert "official" in out["why_recommended"].lower()
    assert _card(out, out["recommended_provider"])["source_role"] == "official"


# ── 60. GDELT marked attribution/rate risk high ──
def test_gdelt_marked_high_risk():
    out = build_next_provider_expansion_pack(no_yield_reason="news_no_records", news_records_count=0)
    g = _card(out, "gdelt")
    assert g["rate_limit_risk"] == "high"
    assert g["attribution_risk"] == "high"


# ── 61. runtime_enabled False + gdelt_executed False ──
def test_runtime_disabled_and_gdelt_not_executed():
    out = build_next_provider_expansion_pack(no_yield_reason="news_no_records")
    assert out["runtime_enabled"] is False
    assert out["gdelt_executed"] is False
    assert out["network_invoked"] is False
    assert out["recommendation_is_planning_not_runtime"] is True
    assert out["runtime_expansion_requires_separate_adr"] is True


# ── 62. source role guard preserved (official vs news roles correct) ──
def test_source_role_guard_preserved():
    out = build_next_provider_expansion_pack(no_yield_reason="news_no_records")
    assert out["source_role_guard_preserved"] is True
    roles = {c["source_id"]: c["source_role"] for c in out["provider_cards"]}
    assert roles["gdelt"] == "news"
    assert roles["ap_reuters_like"] == "news"
    assert roles["federal_register"] == "official"
    assert roles["sec_edgar"] == "official"
    assert roles["official_agency_pr"] == "official"


# ── friendly token "freeze_unsafe" -> TX_FREEZE_UNSAFE -> overlap refine (no new provider) ──
def test_freeze_unsafe_friendly_token_resolves_and_refines():
    out = build_next_provider_expansion_pack(no_yield_reason="freeze_unsafe")
    assert out["resolved_taxonomy_key"] == TX_FREEZE_UNSAFE
    assert out["next_provider_expansion_status"] == NPE_OVERLAP_REFINE
    assert out["recommended_provider"] == "none_refine_overlap_window"
    assert out["next_adr_candidate"] == ""


def test_freeze_unsafe_tx_value_also_resolves():
    # the canonical TX value itself is accepted too (both forms map to TX_FREEZE_UNSAFE).
    out = build_next_provider_expansion_pack(no_yield_reason=TX_FREEZE_UNSAFE)
    assert out["resolved_taxonomy_key"] == TX_FREEZE_UNSAFE
    assert out["next_provider_expansion_status"] == NPE_OVERLAP_REFINE


# ── KO lane present and separate (never merged with EN) ──
def test_ko_lane_present_and_separate():
    out = build_next_provider_expansion_pack(no_yield_reason="news_no_records")
    ko = out["ko_lane_recommendation"]
    assert ko
    assert out["ko_lane_separate"] is True
    assert ko["separate_from_en_lane"] is True
    assert ko["source_role"] == "news_ko"
    # KO sources are not mixed into the EN provider_cards.
    en_ids = {c["source_id"] for c in out["provider_cards"]}
    assert not (en_ids & set(ko["recommended_ko_sources"]))


# ── honesty invariants ──
def test_honesty_invariants():
    out = build_next_provider_expansion_pack(no_yield_reason="news_no_records")
    assert out["aggregator_truth"] is False
    assert out["merge_allowed"] is False
    assert out["same_event_asserted"] is False
    assert out["production_gold_count"] == 0
    assert out["secret_values_exposed"] is False


# ── input echo + unknown reason fail-closed ──
def test_input_echo_and_unknown_fail_closed():
    out = build_next_provider_expansion_pack(no_yield_reason="totally_unknown_reason")
    assert out["input_no_yield_reason"] == "totally_unknown_reason"
    assert out["next_provider_expansion_status"] == NPE_NOT_TRIGGERED
    assert out["recommended_provider"] == "none"


def test_none_reason_not_triggered():
    out = build_next_provider_expansion_pack()
    assert out["input_no_yield_reason"] is None
    assert out["next_provider_expansion_status"] == NPE_NOT_TRIGGERED


# ── credential fields are secret-safe (present/missing semantics only, never values) ──
def test_credential_requirement_secret_safe():
    out = build_next_provider_expansion_pack(no_yield_reason="news_no_records")
    allowed = {"key_free", "key_required", "n/a"}
    for c in out["provider_cards"]:
        assert c["credential_requirement"] in allowed


# ── required output contract (exact keys present) ──
def test_required_output_keys_present():
    out = build_next_provider_expansion_pack(no_yield_reason="news_no_records")
    required = {
        "operation_name", "next_provider_expansion_status", "input_no_yield_reason",
        "resolved_taxonomy_key", "recommended_provider", "why_recommended", "source_role",
        "date_filter_capability", "credential_requirement", "rate_limit_risk", "attribution_risk",
        "canonical_url_risk", "body_availability_risk", "implementation_cost", "next_adr_candidate",
        "ko_lane_recommendation", "provider_cards",
    }
    assert required <= set(out.keys())
    card_keys = {
        "source_id", "source_role", "date_filter_capability", "rate_limit_risk", "attribution_risk",
        "canonical_url_risk", "body_availability_risk", "credential_requirement", "implementation_cost",
        "adapter_status", "why",
    }
    for c in out["provider_cards"]:
        assert card_keys <= set(c.keys())


# ── operation name + sanitized projection ──
def test_operation_name_and_sanitized_projection():
    out = build_next_provider_expansion_pack(no_yield_reason="news_no_records")
    assert out["operation_name"] == OPERATION_NAME
    s = sanitized_next_provider_expansion_pack(out)
    assert set(s.keys()) == {
        "next_provider_expansion_status", "resolved_taxonomy_key", "recommended_provider",
        "rate_limit_risk", "attribution_risk", "ko_lane_separate", "runtime_enabled", "gdelt_executed",
    }
    assert s["next_provider_expansion_status"] == NPE_NEWS_BREADTH
    assert s["gdelt_executed"] is False
