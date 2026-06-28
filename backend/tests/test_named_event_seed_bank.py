"""ADR#81 — named single-event seed bank 테스트(§13: 18~24·broad reject·same_event 단정 0).

network 0 · merge 0 · LLM 0 · same_event 단정 0. validator 가 §6 broad/bare/placeholder seed 를 거르고 named
single-event shape 만 통과시키는지, curated bank 가 필수 필드를 갖는지 검증."""
from __future__ import annotations

from backend.app.tools.named_event_seed_bank import (
    build_named_event_seed_bank,
    validate_date_pinned_named_event,
    validate_named_single_event_seed,
)


def _named_seed(**over):
    base = {
        "seed_id": "t", "seed_text": "US Federal Reserve FOMC rate decision",
        "named_entity": "US Federal Reserve FOMC", "event_phrase": "FOMC rate decision announcement",
        "date_window": "1d", "provider_coverage_hypothesis": "guardian+nyt+gdelt",
    }
    base.update(over)
    return base


def test_named_single_event_seed_accepted():
    """§13-19: named single-event seed 통과."""
    v = validate_named_single_event_seed(_named_seed())
    assert v["accepted"] is True
    assert v["is_named_single_event_shape"] is True


def test_broad_seed_rejected():
    """§13-18: broad/category seed reject(§6 rejected 예시)."""
    for text, ent in [
        ("Supreme Court ruling", "Supreme Court"),
        ("Federal Reserve", "Federal Reserve"),
        ("election", "election"),
        ("climate change", "climate change"),
        ("stock market", "stock market"),
    ]:
        v = validate_named_single_event_seed(
            {"seed_id": "b", "seed_text": text, "named_entity": ent,
             "event_phrase": text, "date_window": "1d",
             "provider_coverage_hypothesis": "broad"})
        assert v["accepted"] is False, f"broad seed should reject: {text}"


def test_validator_discriminates_bare_vs_specific_entity():
    """bare 'Federal Reserve' reject 하되 'US Federal Reserve FOMC' (specific) 는 통과 — discrimination."""
    bare = validate_named_single_event_seed(
        {"seed_id": "bare", "seed_text": "Federal Reserve", "named_entity": "Federal Reserve",
         "event_phrase": "policy", "date_window": "1d", "provider_coverage_hypothesis": "x"})
    specific = validate_named_single_event_seed(_named_seed())
    assert bare["accepted"] is False
    assert specific["accepted"] is True


def test_placeholder_entity_rejected():
    """placeholder(<Party>/operator fills) 엔티티는 named single-event 아님 — reject."""
    v = validate_named_single_event_seed(
        _named_seed(named_entity="<Acquirer> – <Target> (operator fills)"))
    assert v["accepted"] is False
    assert "placeholder_entity_requires_operator_specification" in v["rejection_reasons"]


def test_missing_required_fields_rejected():
    """필수 구조 필드 누락 → reject(§13-20~23 역검증)."""
    for missing in ("named_entity", "event_phrase", "date_window", "provider_coverage_hypothesis"):
        seed = _named_seed()
        seed[missing] = ""
        v = validate_named_single_event_seed(seed)
        assert v["accepted"] is False
        assert f"missing_{missing}" in v["rejection_reasons"]


def test_broad_date_window_rejected():
    """7d/ongoing 등 broad window reject(1d 또는 ISO date 만 허용)."""
    assert validate_named_single_event_seed(_named_seed(date_window="7d"))["accepted"] is False
    assert validate_named_single_event_seed(_named_seed(date_window="ongoing"))["accepted"] is False
    assert validate_named_single_event_seed(_named_seed(date_window="2026-06-27"))["accepted"] is True


def test_bank_seeds_have_required_fields():
    """§13-20~23: bank 의 accepted seed 는 named_entity·event_phrase·date_window·provider_coverage_hypothesis 보유."""
    bank = build_named_event_seed_bank()
    accepted = [s for s in bank["seed_bank"] if s["accepted"]]
    assert len(accepted) >= 2
    for s in accepted:
        assert s["named_entity"] and "<" not in s["named_entity"]
        assert s["event_phrase"]
        assert s["date_window"]
        assert s["provider_coverage_hypothesis"]


def test_bank_rejects_all_broad_examples():
    """validator 가 §6 broad 자가검증 예시를 모두 reject."""
    bank = build_named_event_seed_bank()
    assert bank["validator_rejects_all_broad_examples"] is True
    assert bank["broad_seed_rejected_count"] == bank["broad_seed_examples_tested"]


def test_selected_seed_is_live_allowed_and_named():
    """선정된 다음 live-run seed 는 accepted ∧ live_run_allowed_if_approved."""
    bank = build_named_event_seed_bank()
    sel = bank["selected_seed_for_next_live_run"]
    assert sel is not None
    assert sel["live_run_allowed_if_approved"] is True
    assert sel["accepted"] is True
    assert bank["selected_seed_id"] == sel["seed_id"]


def test_no_same_event_truth_and_no_gold():
    """§13-24: same_event 단정 0 · production gold 0 · merge 0."""
    bank = build_named_event_seed_bank()
    assert bank["same_event_truth_asserted"] is False
    assert bank["seed_is_candidate_generation_not_same_event_proof"] is True
    assert bank["event_occurrence_verified"] is False
    assert bank["production_gold_count"] == 0
    assert bank["merge_allowed"] is False
    assert bank["llm_invoked"] is False
    assert bank["embedding_invoked"] is False
    # 개별 seed 도 same_event 미단정.
    for s in bank["seed_bank"]:
        assert s["same_event_asserted"] is False
        assert s["provenance"] == "code_proposed_named_shape"


# ── ADR#82 date-pin 게이트(§12: 8~12) ────────────────────────────────────────────────────────────────────────
def test_date_pin_fomc_without_occurrence_date_rejected():
    """§12-8: occurrence_date 없는 named seed 는 date_pinned=False(missing_occurrence_date)."""
    v = validate_date_pinned_named_event(_named_seed())   # occurrence_date 없음.
    assert v["date_pinned"] is False
    assert v["occurrence_date"] is None
    assert "missing_occurrence_date" in v["rejection_reasons"]


def test_date_pin_fomc_with_iso_occurrence_date_accepted():
    """§12-9·11: occurrence_date(ISO) 있으면 date_pinned=True·실제 occurrence 기록."""
    v = validate_date_pinned_named_event(_named_seed(occurrence_date="2026-06-17"))
    assert v["date_pinned"] is True
    assert v["occurrence_date"] == "2026-06-17"
    assert v["named_shape_ok"] is True


def test_date_pin_non_iso_occurrence_date_rejected():
    """occurrence_date 가 ISO(YYYY-MM-DD) 아니면 reject."""
    for bad in ("June 17 2026", "2026/06/17", "next week", "2026-6-17"):
        v = validate_date_pinned_named_event(_named_seed(occurrence_date=bad))
        assert v["date_pinned"] is False
        assert "occurrence_date_not_iso_yyyy_mm_dd" in v["rejection_reasons"]


def test_date_pin_broad_seed_rejected_even_with_date():
    """§12-10: broad seed 는 occurrence_date 가 있어도 named shape 실패로 date_pinned=False."""
    v = validate_date_pinned_named_event(
        {"seed_id": "b", "seed_text": "Federal Reserve", "named_entity": "Federal Reserve",
         "event_phrase": "policy", "date_window": "1d", "provider_coverage_hypothesis": "broad",
         "occurrence_date": "2026-06-17"})
    assert v["date_pinned"] is False
    assert "bare_broad_entity" in v["rejection_reasons"]


def test_date_pin_does_not_assert_same_event_or_occurrence():
    """§12-12: date_pinned=True 여도 event_occurrence_verified=False·same_event_asserted=False(불변)."""
    v = validate_date_pinned_named_event(_named_seed(occurrence_date="2026-06-17"))
    assert v["date_pinned"] is True
    assert v["event_occurrence_verified"] is False
    assert v["same_event_asserted"] is False
