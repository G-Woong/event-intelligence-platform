"""ADR#94 — unified live result closure tests.

검증: missing payload → operator-confirmed-ready package next action·news gap → provider expansion·official gap →
official adjustment·overlap gap → query/date/action adjustment·freeze 후보 → hardening 필요·closure 는 same_event
truth 단정 0·gold 증가 0·R1 next action 비어있지 않음. closure 는 diagnostic·truth/gold 아님.
"""
from __future__ import annotations

from backend.app.tools.first_freeze_package_hardening import FH_SAFE
from backend.app.tools.news_breadth_trigger import (
    NBT_OFFICIAL_FIRST,
    NBT_OVERLAP_REFINE,
    NBT_RECOMMEND_NEWS_BREADTH,
)
from backend.app.tools.next_provider_expansion_pack import (
    NPE_NEWS_BREADTH,
    NPE_OFFICIAL_FIRST,
)
from backend.app.tools.official_news_live_acquisition import (
    ONL_NEWS_NO_RECORDS,
    ONL_OFFICIAL_NO_RECORDS,
)
from backend.app.tools.unified_live_result_closure import (
    OPERATION_NAME,
    build_unified_live_result_closure,
    sanitized_unified_live_result_closure,
)


def _safe_pair() -> dict:
    """reviewer-facing safe freeze artifact(first_freeze_package_hardening._safe_pair 템플릿 미러)."""
    return {
        "pair_id": "oxn_0001",
        "official_record": {
            "record_type": "official_document",
            "source_id": "federal_register",
            "canonical_url": "https://www.federalregister.gov/documents/2026/06/25/epa-rule",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "EPA final rule on greenhouse gas emissions standards",
        },
        "news_record": {
            "record_type": "news_article",
            "source_id": "guardian",
            "canonical_url": "https://www.theguardian.com/environment/2026/jun/25/epa-emissions",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "EPA tightens vehicle emissions standards",
        },
        "shared_tokens": ["epa", "emissions"],
        "date_proximity_days": 0,
    }


def _entity_blocked_candidate() -> dict:
    """모든 구조 차원은 통과하되 entity 토큰만 비공유 → overlap blocked_dimension=entity_overlap 인 bridge 후보."""
    return {
        "source_role_official": "official",
        "source_role_news": "news",
        "both_canonical_present": True,
        "both_published_present": True,
        "official_in_window": True,
        "news_in_window": True,
        "date_proximity_days": 0,
        "shared_tokens": ["alpha", "beta"],
    }


# ── missing payload closure → operator-confirmed-ready package next action ──
def test_missing_payload_closure_emits_operator_package():
    out = build_unified_live_result_closure(real_payload_present=False)
    assert out["unified_live_closure_status"] == "closed_missing_payload"
    assert out["dominant_gap"] == "missing_payload"
    assert "operator_confirmed_ready_package" in out["operator_next_action"]
    assert "payload" in out["recommended_iteration"].lower()


# ── news gap closure → provider expansion(trigger + pack 둘 다 news breadth 권고) ──
def test_news_gap_closure_emits_provider_expansion():
    out = build_unified_live_result_closure(
        live_query_executed=True, real_payload_present=True,
        acquisition_out={"official_news_live_status": ONL_NEWS_NO_RECORDS},
        official_records_count=3, news_records_count=0)
    assert out["news_breadth_trigger_status"] == NBT_RECOMMEND_NEWS_BREADTH
    assert out["next_provider_expansion_status"] == NPE_NEWS_BREADTH
    assert out["dominant_gap"] == "news_side_gap"
    assert "provider" in out["recommended_iteration"].lower()
    assert out["unified_live_closure_status"] == "closed_no_yield_news_no_records"


# ── official gap closure → official adjustment(news breadth 먼저 권하지 않음) ──
def test_official_gap_closure_emits_official_adjustment():
    out = build_unified_live_result_closure(
        live_query_executed=True, real_payload_present=True,
        acquisition_out={"official_news_live_status": ONL_OFFICIAL_NO_RECORDS},
        official_records_count=0, news_records_count=5)
    assert out["news_breadth_trigger_status"] == NBT_OFFICIAL_FIRST
    assert out["next_provider_expansion_status"] == NPE_OFFICIAL_FIRST
    assert out["dominant_gap"] == "official_side_gap"
    assert "official" in out["recommended_iteration"].lower()


# ── overlap gap closure → query/date/action adjustment(blocked dimension 입력) ──
def test_overlap_gap_closure_emits_query_date_action_adjustment():
    out = build_unified_live_result_closure(
        live_query_executed=True, real_payload_present=True,
        overlap_candidates=[_entity_blocked_candidate()],
        seed={"agency_or_entity": "Gamma Authority", "action_phrase": "delta ruling"},
        official_records_count=2, news_records_count=2)
    assert out["overlap_blocked_dimension"] == "entity_overlap"
    assert out["news_breadth_trigger_status"] == NBT_OVERLAP_REFINE
    assert out["dominant_gap"] == "overlap_gap"
    it = out["recommended_iteration"].lower()
    assert "query" in it and "date" in it and "action" in it


# ── freeze candidate closure → hardening 필요(safe artifact → readiness 가 hardening 결과 반영) ──
def test_freeze_candidate_closure_requires_hardening():
    out = build_unified_live_result_closure(
        live_query_executed=True, real_payload_present=True, freeze_artifact=_safe_pair())
    assert out["unified_live_closure_status"] == "closed_freeze_candidate"
    assert out["dominant_gap"] == "freeze_candidate"
    assert out["freeze_readiness_status"] == FH_SAFE
    assert out["freeze_artifact_safe"] is True
    assert "harden" in out["recommended_iteration"].lower()


# ── closure 는 same_event truth 를 단정하지 않는다 ──
def test_closure_never_sets_same_event_truth():
    out = build_unified_live_result_closure(real_payload_present=True, freeze_artifact=_safe_pair())
    assert out["same_event_asserted"] is False
    assert out["is_truth"] is False
    assert out["merge_allowed"] is False


# ── closure 는 gold 를 증가시키지 않는다 ──
def test_closure_never_increases_gold():
    out = build_unified_live_result_closure(real_payload_present=True, freeze_artifact=_safe_pair())
    assert out["production_gold_count"] == 0
    assert out["increases_gold"] is False


# ── closure 는 R1 next action 을 낸다(비어있지 않음) ──
def test_closure_emits_r1_next_action():
    missing = build_unified_live_result_closure(real_payload_present=False)
    assert missing["r1_next_action"]
    frozen = build_unified_live_result_closure(real_payload_present=True, freeze_artifact=_safe_pair())
    assert frozen["r1_next_action"]


# ── 필수 출력 키 계약(전부 존재) ──
def test_required_output_keys_present():
    out = build_unified_live_result_closure()
    required = {
        "unified_live_closure_status", "live_query_executed", "live_no_yield_taxonomy_status",
        "taxonomy_next_action", "overlap_diagnostic_status", "overlap_blocked_dimension",
        "news_breadth_trigger_status", "next_provider_expansion_status", "freeze_readiness_status",
        "r1_next_action", "operator_next_action", "recommended_iteration",
        # invariants.
        "is_truth", "same_event_asserted", "merge_allowed", "llm_invoked", "network_invoked",
        "production_gold_count", "increases_gold",
    }
    assert required <= set(out.keys())
    assert out["operation_name"] == OPERATION_NAME


# ── network/LLM 0 + sanitized 투영(상위 출력의 subset) ──
def test_invariants_and_sanitized_projection():
    out = build_unified_live_result_closure()
    assert out["llm_invoked"] is False
    assert out["network_invoked"] is False
    assert out["no_live_result_without_payload"] is True
    assert out["no_candidate_no_freeze"] is True
    s = sanitized_unified_live_result_closure(out)
    assert set(s.keys()) <= set(out.keys())
    assert s["unified_live_closure_status"] == out["unified_live_closure_status"]
