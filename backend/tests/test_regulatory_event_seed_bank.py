"""ADR#87 — regulatory-class event seed bank 테스트(§19 tests 6~13·broad reject·official×news role·same_event 0)."""
from __future__ import annotations

from backend.app.tools.regulatory_event_seed_bank import (
    build_regulatory_event_seed_bank,
    validate_regulatory_seed,
)


def _valid_seed(**overrides) -> dict:
    base = {
        "seed_id": "epa_test",
        "regulatory_domain": "agency final rule",
        "official_provider": "federal_register",
        "news_providers": ["guardian", "nyt"],
        "agency": "Environmental Protection Agency",
        "entity": "EPA vehicle emissions standard",
        "action_phrase": "final rule on greenhouse gas emissions standards",
        "document_type": "Rule",
        "official_query": "Environmental Protection Agency greenhouse gas emissions final rule",
        "news_query": "EPA emissions rule",
        "date_window_start": "2026-06-25",
        "date_window_end": "2026-06-26",
    }
    base.update(overrides)
    return base


# ── §19 test 6: valid regulatory seed accepted ──────────────────────────────────────────────────────────
def test_06_valid_regulatory_seed_accepted():
    v = validate_regulatory_seed(_valid_seed())
    assert v["accepted"] is True
    assert v["rejection_reasons"] == []
    assert v["is_regulatory_event_shape"] is True
    assert v["has_official_provider"] and v["has_news_provider"]
    assert v["has_date_window"] and v["has_entity_or_agency"] and v["has_action_phrase"]
    assert v["is_not_broad_topic"] is True


# ── §19 test 7: seed without date window rejected ───────────────────────────────────────────────────────
def test_07_seed_without_date_window_rejected():
    v = validate_regulatory_seed(_valid_seed(date_window_start="", date_window_end=""))
    assert v["accepted"] is False
    assert "missing_date_window" in v["rejection_reasons"]
    assert v["has_date_window"] is False


def test_07b_seed_with_non_iso_date_window_rejected():
    v = validate_regulatory_seed(_valid_seed(date_window_start="June 25", date_window_end="June 26"))
    assert v["accepted"] is False
    assert "date_window_not_iso_yyyy_mm_dd" in v["rejection_reasons"]


# ── §19 test 8: seed without agency/entity rejected ─────────────────────────────────────────────────────
def test_08_seed_without_agency_or_entity_rejected():
    v = validate_regulatory_seed(_valid_seed(agency="", entity=""))
    assert v["accepted"] is False
    assert "missing_agency_or_entity" in v["rejection_reasons"]


def test_08b_placeholder_agency_rejected():
    v = validate_regulatory_seed(_valid_seed(agency="<Agency operator fills>", entity=""))
    assert v["accepted"] is False
    assert "placeholder_agency_or_entity_requires_operator_specification" in v["rejection_reasons"]


# ── §19 test 9: seed without action phrase rejected ─────────────────────────────────────────────────────
def test_09_seed_without_action_phrase_rejected():
    v = validate_regulatory_seed(_valid_seed(action_phrase=""))
    assert v["accepted"] is False
    assert "missing_action_phrase" in v["rejection_reasons"]


# ── §19 test 10: broad generic seed rejected ────────────────────────────────────────────────────────────
def test_10_broad_generic_seed_rejected():
    # entity/action/queries 가 전부 generic 'enforcement' → broad_or_generic_topic.
    v = validate_regulatory_seed(_valid_seed(
        agency="", entity="enforcement", action_phrase="enforcement",
        official_query="enforcement", news_query="enforcement"))
    assert v["accepted"] is False
    assert "broad_or_generic_topic" in v["rejection_reasons"]
    assert v["is_not_broad_topic"] is False


def test_10b_disallowed_regulatory_domain_rejected():
    v = validate_regulatory_seed(_valid_seed(regulatory_domain="generic stock market"))
    assert v["accepted"] is False
    assert "regulatory_domain_not_allowed" in v["rejection_reasons"]


# ── §19 test 11/12: community-only / market-only news provider rejected (anchor 승격 금지) ────────────────
def test_11_community_only_news_provider_rejected():
    v = validate_regulatory_seed(_valid_seed(news_providers=["community"]))
    assert v["accepted"] is False
    assert "missing_news_provider" in v["rejection_reasons"]
    assert "non_anchor_news_provider" in v["rejection_reasons"]


def test_12_market_only_news_provider_rejected():
    v = validate_regulatory_seed(_valid_seed(news_providers=["market"]))
    assert v["accepted"] is False
    assert "non_anchor_news_provider" in v["rejection_reasons"]


def test_12b_missing_official_provider_rejected():
    v = validate_regulatory_seed(_valid_seed(official_provider="guardian"))
    assert v["accepted"] is False
    assert "missing_official_provider" in v["rejection_reasons"]


def test_12c_missing_news_query_rejected():
    v = validate_regulatory_seed(_valid_seed(news_query=""))
    assert v["accepted"] is False
    assert "missing_news_query" in v["rejection_reasons"]


# ── §19 test 13: seed keeps same_event_asserted=false (모든 경로) ────────────────────────────────────────
def test_13_seed_keeps_same_event_asserted_false():
    for seed in (_valid_seed(), _valid_seed(agency="", entity="")):
        v = validate_regulatory_seed(seed)
        assert v["same_event_asserted"] is False
        assert v["reviewer_routing_only"] is True
        assert v["event_occurrence_verified"] is False


# ── build bank: ready·broad self-test·selection·invariants ──────────────────────────────────────────────
def test_build_bank_ready_and_selectable():
    bank = build_regulatory_event_seed_bank()
    assert bank["regulatory_event_seed_bank_ready"] is True
    assert bank["regulatory_seed_count"] >= 1
    # 적어도 하나의 live-run-allowed seed 가 선정된다(fully-specified EPA final rule).
    assert bank["selected_seed_id"] is not None
    selected = bank["selected_seed_for_next_live_run"]
    assert selected["live_run_allowed_if_approved"] is True
    assert selected["official_provider"] == "federal_register"
    # official_query ≠ news_query(분리).
    assert selected["official_query"] != selected["news_query"]


def test_build_bank_rejects_all_broad_examples():
    bank = build_regulatory_event_seed_bank()
    assert bank["validator_rejects_all_broad_examples"] is True
    assert bank["broad_seed_rejected_count"] == bank["broad_seed_examples_tested"]


def test_build_bank_invariants():
    bank = build_regulatory_event_seed_bank()
    assert bank["same_event_truth_asserted"] is False
    assert bank["official_news_role_separated"] is True
    assert bank["merge_allowed"] is False
    assert bank["llm_invoked"] is False
    assert bank["embedding_invoked"] is False
    assert bank["db_write"] is False
    assert bank["production_gold_count"] == 0


def test_build_bank_template_seeds_not_live_selectable():
    # respondent/target 미특정 template seed(sec/fda/ofac)는 entity 가 "operator fills" placeholder 라 **rejected**
    # (accepted=False)·따라서 live 선정 불가(adversarial NIT: "accepted 여도"가 아니라 reject 가 정확·더 안전).
    bank = build_regulatory_event_seed_bank()
    for s in bank["seed_bank"]:
        if s["seed_id"] in ("sec_enforcement_settlement", "fda_safety_action", "ofac_sanction_notice"):
            assert s["accepted"] is False   # placeholder entity → reject(not merely non-selectable).
            assert "placeholder_agency_or_entity_requires_operator_specification" in s["rejection_reasons"]
            assert s["seed_id"] not in bank["selectable_seed_ids"]
