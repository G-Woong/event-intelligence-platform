"""ADR#92 §10 — news breadth trigger tests.

검증: news_no_records→news breadth·no_in_window_news→provider/date·official_no_records→news breadth 먼저 권하지
않음·freeze_unsafe→freeze safety·GDELT 실행 0·rate/attribution risk 가시·source role guard 보존·truth 0.
"""
from __future__ import annotations

from backend.app.tools.live_no_yield_taxonomy import (
    TX_FREEZE_UNSAFE,
    TX_NEWS_NO_RECORDS,
    TX_NO_IN_WINDOW_NEWS,
    TX_NO_OVERLAP,
    TX_OFFICIAL_NO_RECORDS,
)
from backend.app.tools.news_breadth_trigger import (
    NBT_FREEZE_SAFETY,
    NBT_NOT_TRIGGERED,
    NBT_OFFICIAL_FIRST,
    NBT_OVERLAP_REFINE,
    NBT_RECOMMEND_NEWS_BREADTH,
    NBT_RECOMMEND_PROVIDER_DATE,
    build_news_breadth_trigger,
    sanitized_news_breadth_trigger,
)
from backend.app.tools.official_news_overlap_diagnostics import (
    DIM_ACTION,
    DIM_ENTITY,
    DIM_IN_WINDOW,
)


# ── 24. news_no_records -> recommend news breadth ──
def test_news_no_records_recommends_news_breadth():
    out = build_news_breadth_trigger(
        live_no_yield_taxonomy_status=TX_NEWS_NO_RECORDS, official_records_count=3, news_records_count=0)
    assert out["news_breadth_trigger_status"] == NBT_RECOMMEND_NEWS_BREADTH
    assert any("gdelt" in e.lower() for e in out["recommended_provider_expansion"])
    assert "news breadth" in out["recommended_action"].lower()


# ── 25. no_in_window_news -> recommend provider/date strategy ──
def test_no_in_window_news_recommends_provider_date():
    out = build_news_breadth_trigger(
        live_no_yield_taxonomy_status=TX_NO_IN_WINDOW_NEWS, official_records_count=3, news_records_count=5,
        in_window_news_count=0)
    assert out["news_breadth_trigger_status"] == NBT_RECOMMEND_PROVIDER_DATE
    assert any("federal_register" in e for e in out["recommended_provider_expansion"])


def test_blocked_dimension_in_window_recommends_provider_date():
    out = build_news_breadth_trigger(overlap_blocked_dimension=DIM_IN_WINDOW,
                                     official_records_count=2, news_records_count=2)
    assert out["news_breadth_trigger_status"] == NBT_RECOMMEND_PROVIDER_DATE


# ── 26. official_no_records -> do not recommend news breadth first ──
def test_official_no_records_does_not_recommend_news_breadth_first():
    out = build_news_breadth_trigger(
        live_no_yield_taxonomy_status=TX_OFFICIAL_NO_RECORDS, official_records_count=0, news_records_count=5)
    assert out["news_breadth_trigger_status"] == NBT_OFFICIAL_FIRST
    # news breadth 를 먼저 권하지 않는다 — GDELT 확장 후보가 비어 있음.
    assert out["recommended_provider_expansion"] == [] or all(
        "gdelt" not in e.lower() for e in out["recommended_provider_expansion"])
    assert "official" in out["recommended_action"].lower()


def test_official_gap_by_count_official_first():
    # status 미주입이어도 official=0·news>0 이면 official-first.
    out = build_news_breadth_trigger(official_records_count=0, news_records_count=4)
    assert out["news_breadth_trigger_status"] == NBT_OFFICIAL_FIRST


# ── 27. bridge_candidate_found_but_freeze_unsafe -> recommend freeze safety fix ──
def test_freeze_unsafe_recommends_freeze_safety():
    out = build_news_breadth_trigger(
        live_no_yield_taxonomy_status=TX_FREEZE_UNSAFE, official_records_count=2, news_records_count=2,
        bridge_candidate_count=1)
    assert out["news_breadth_trigger_status"] == NBT_FREEZE_SAFETY
    assert "freeze" in out["recommended_action"].lower()


# ── 28. GDELT trigger does not run GDELT ──
def test_gdelt_not_executed():
    out = build_news_breadth_trigger(
        live_no_yield_taxonomy_status=TX_NEWS_NO_RECORDS, official_records_count=3, news_records_count=0)
    assert out["gdelt_executed"] is False
    assert out["network_invoked"] is False
    assert out["gdelt_result_is_truth"] is False
    assert out["runtime_expansion_requires_separate_adr"] is True


# ── 29. attribution risk visible ──
def test_attribution_risk_visible():
    out = build_news_breadth_trigger(live_no_yield_taxonomy_status=TX_NEWS_NO_RECORDS, news_records_count=0,
                                     official_records_count=2)
    assert out["attribution_risk"] == "high"
    assert out["source_role_risk"]


# ── 30. rate risk visible ──
def test_rate_risk_visible():
    out = build_news_breadth_trigger(live_no_yield_taxonomy_status=TX_NEWS_NO_RECORDS, news_records_count=0,
                                     official_records_count=2)
    assert out["rate_limit_risk"] == "high"


# ── §10. overlap gap -> refine query (not breadth) ──
def test_no_overlap_recommends_query_refinement():
    out = build_news_breadth_trigger(
        live_no_yield_taxonomy_status=TX_NO_OVERLAP, official_records_count=3, news_records_count=3)
    assert out["news_breadth_trigger_status"] == NBT_OVERLAP_REFINE
    assert "refine" in out["recommended_action"].lower()
    # query 정밀화이지 source breadth 가 아니다 → 확장 후보 비어 있음.
    assert out["recommended_provider_expansion"] == []


def test_entity_dimension_recommends_refinement():
    out = build_news_breadth_trigger(overlap_blocked_dimension=DIM_ENTITY,
                                     official_records_count=2, news_records_count=2)
    assert out["news_breadth_trigger_status"] == NBT_OVERLAP_REFINE


def test_action_dimension_recommends_refinement():
    out = build_news_breadth_trigger(overlap_blocked_dimension=DIM_ACTION,
                                     official_records_count=2, news_records_count=2)
    assert out["news_breadth_trigger_status"] == NBT_OVERLAP_REFINE


# ── §10. no gap -> not triggered ──
def test_no_gap_not_triggered():
    out = build_news_breadth_trigger(official_records_count=3, news_records_count=3)
    assert out["news_breadth_trigger_status"] == NBT_NOT_TRIGGERED
    assert out["recommended_provider_expansion"] == []


# ── §10. source role guard preserved + no merge/same_event ──
def test_invariants_preserved():
    out = build_news_breadth_trigger(live_no_yield_taxonomy_status=TX_NEWS_NO_RECORDS, news_records_count=0,
                                     official_records_count=2)
    assert out["source_role_guard_preserved"] is True
    assert out["merge_allowed"] is False
    assert out["same_event_asserted"] is False
    assert out["production_gold_count"] == 0


# ── sanitized projection (frontier 용) ──
def test_sanitized_projection_keys():
    out = build_news_breadth_trigger(live_no_yield_taxonomy_status=TX_NEWS_NO_RECORDS, news_records_count=0,
                                     official_records_count=2)
    s = sanitized_news_breadth_trigger(out)
    assert set(s.keys()) == {
        "news_breadth_trigger_status", "recommended_provider_expansion", "gdelt_candidate_status",
        "rate_limit_risk", "attribution_risk", "gdelt_executed",
    }
