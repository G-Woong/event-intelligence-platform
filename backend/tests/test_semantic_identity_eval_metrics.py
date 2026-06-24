from __future__ import annotations

"""Semantic adjudicator evaluation metrics 단위 (ADR#43, R-IdentityEvalDataset).

현재 deterministic adjudicator 를 labeled fixture 에 적용해 precision/FPR/recall/coverage/breakdown 을 측정.
**핵심**: 진단 세트에서 현재 adjudicator 가 merge gate(precision≥0.98·FPR≤0.01·hard-neg FP=0)를 **충족하지
못함**을 정직하게 입증 → 자동 병합은 켜지지 않는다(auto_merge_enabled=False). 평가 전용·병합 0.
"""

from pathlib import Path

from backend.app.services.identity_eval_dataset import (
    ADJ_LIKELY_SAME,
    LABEL_SAME,
    MERGE_GATE,
    evaluate_adjudicator,
    load_eval_pairs,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "identity_eval_pairs.jsonl"


def _pairs():
    return load_eval_pairs(_FIXTURE)


def _metrics():
    return evaluate_adjudicator(_pairs())


# ── 9. all-correct(clean TP) subset → precision 1.0 ──────────────────────────────
def test_clean_positive_subset_precision_one():
    clean = [p for p in _pairs() if p.pair_id.startswith("tp_")]
    m = evaluate_adjudicator(clean)
    assert m["overall"]["likely_same_precision"] == 1.0   # 쉬운 동일사건은 정확히 likely_same
    assert m["overall"]["same_event_recall"] == 1.0


# ── 10. hard-negative false positive 반영(현재 adjudicator 실패모드) ───────────────
def test_hard_negative_false_positive_detected():
    m = _metrics()
    assert m["hard_negative_false_positive"] >= 1           # 템플릿 충돌이 likely_same 오판(FP)
    # hard_negative risk-tag subset 에서 FP 가 잡힌다.
    hn = m["by_risk_tag"].get("hard_negative")
    assert hn is not None and hn["fp"] >= 1


# ── 11·12. ambiguous/insufficient rate·coverage 산출 ──────────────────────────────
def test_rates_and_coverage_computed():
    o = _metrics()["overall"]
    assert 0.0 <= o["ambiguous_rate"] <= 1.0
    assert o["insufficient_rate"] > 0.0                     # non-publishable/generic/paraphrase 다수
    assert 0.0 <= o["coverage"] <= 1.0


# ── 13·14·15. by_language / by_source_type / by_risk_tag breakdown ────────────────
def test_breakdowns_present():
    m = _metrics()
    assert {"ko", "en", "mixed"} <= set(m["by_language"])
    assert any("community" in k for k in m["by_source_type"])
    assert "paraphrase" in m["by_risk_tag"] and "templated" in m["by_risk_tag"]


# ── 16·17. 한국어 subset / mixed subset metric ───────────────────────────────────
def test_korean_subset_metric():
    m = _metrics()
    ko = m["by_language"]["ko"]
    assert ko["count"] >= 3
    # 한국어에도 template 충돌 FP 가 있어 precision < 1.0(영어와 동일 실패모드·캘리브레이션 미완).
    assert ko["likely_same_precision"] is not None and ko["likely_same_precision"] < 1.0


# ── 18~24. merge gate 미충족·자동 병합 OFF(핵심 정직 계약) ────────────────────────
def test_merge_gate_not_passed_and_auto_merge_off():
    m = _metrics()
    o = m["overall"]
    # 현재 deterministic adjudicator 는 진단 세트에서 gate 미달(precision<0.98·FPR>0.01·hard-neg FP>0).
    assert o["likely_same_precision"] < MERGE_GATE["likely_same_precision_min"]
    assert o["likely_same_false_positive_rate"] > MERGE_GATE["likely_same_false_positive_rate_max"]
    assert m["merge_gate"]["passed"] is False
    # **불변**: gate 충족 여부와 무관하게 자동 병합은 절대 켜지지 않는다.
    assert m["merge_gate"]["auto_merge_enabled"] is False
    assert m["auto_merged"] == 0


def test_recall_below_one_due_to_paraphrase_fn():
    # 패러프레이즈/번역 동일사건을 deterministic 층이 놓침(FN) → recall < 1.0(embedding/entity 필요).
    o = _metrics()["overall"]
    assert o["same_event_recall"] < 1.0


def test_evaluate_deterministic():
    a = _metrics()["overall"]
    b = _metrics()["overall"]
    assert a == b                                          # 같은 fixture+adjudicator → 같은 metric


def test_no_pairs_safe():
    m = evaluate_adjudicator([])
    assert m["overall"]["count"] == 0 and m["auto_merged"] == 0
    assert m["merge_gate"]["auto_merge_enabled"] is False
