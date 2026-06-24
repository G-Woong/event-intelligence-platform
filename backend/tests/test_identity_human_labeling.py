from __future__ import annotations

"""Human-labeled gold workflow + gold metric harness 단위 (ADR#44, R-IdentityHumanLabeling).

gold schema/provenance 검증·워크시트→gold 라운드트립·gold-only metric·한국어/혼합 breakdown·merge readiness
(자동 병합 OFF 불변)를 잠근다. 실 human-reviewed production gold 는 아직 없음(샘플 workflow 부분종결).
"""

import json
from pathlib import Path

import pytest

from backend.app.services.identity_eval_dataset import load_eval_pairs
from backend.app.services.identity_human_labeling import (
    GOLD_MERGE_MIN_KOREAN_GOLD,
    GOLD_MERGE_MIN_LIVE_GOLD,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    GoldPair,
    compare_fixture_vs_gold_metrics,
    evaluate_adjudicator_on_gold,
    evaluate_gold_merge_readiness,
    generate_gold_eval_report,
    gold_to_eval_pair,
    load_gold_pairs,
    promote_worksheet_to_gold,
    summarize_labeling_backlog,
    write_gold_jsonl,
)

_GOLD_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "identity_gold_pairs.sample.jsonl"
_EVAL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "identity_eval_pairs.jsonl"


def _grow(**kw):
    base = {
        "pair_id": "g1", "label": "same_event", "language": "en",
        "source_type_left": "article", "source_type_right": "article",
        "title_left": "Federal Reserve raises benchmark interest rates today",
        "title_right": "Federal Reserve raises benchmark interest rates today",
        "observed_at_left": "2026-06-24T09:00:00Z", "observed_at_right": "2026-06-24T10:00:00Z",
        "reviewed_by": "sample_reviewer", "reviewed_at": "2026-06-24T18:00:00Z",
        "review_status": "gold", "label_confidence": "high", "dataset_source": "live_derived",
    }
    base.update(kw)
    return base


def _write(tmp_path, rows):
    p = tmp_path / "gold.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


# ── 1. valid gold JSONL loads ──────────────────────────────────────────────────────
def test_load_sample_gold_ok():
    pairs = load_gold_pairs(_GOLD_FIXTURE)
    assert len(pairs) >= 12
    assert all(isinstance(p, GoldPair) for p in pairs)
    # provenance 필수 채워짐.
    assert all(p.reviewed_by and p.reviewed_at and p.review_status and p.label_confidence for p in pairs)


# ── 2·3·4. provenance 누락/형식 거부 ─────────────────────────────────────────────────
def test_missing_reviewed_by_rejected(tmp_path):
    row = _grow(); del row["reviewed_by"]
    with pytest.raises(ValueError, match="missing required keys"):
        load_gold_pairs(_write(tmp_path, [row]))


def test_missing_reviewed_at_rejected(tmp_path):
    row = _grow(); del row["reviewed_at"]
    with pytest.raises(ValueError, match="missing required keys"):
        load_gold_pairs(_write(tmp_path, [row]))


def test_invalid_reviewed_at_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid reviewed_at"):
        load_gold_pairs(_write(tmp_path, [_grow(reviewed_at="yesterday afternoon")]))


# ── 5·6·7. enum 거부 ────────────────────────────────────────────────────────────────
def test_invalid_review_status_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid review_status"):
        load_gold_pairs(_write(tmp_path, [_grow(review_status="approved")]))


def test_invalid_label_confidence_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid label_confidence"):
        load_gold_pairs(_write(tmp_path, [_grow(label_confidence="very_high")]))


def test_invalid_label_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid label"):
        load_gold_pairs(_write(tmp_path, [_grow(label="merge_now")]))


def test_invalid_dataset_source_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid dataset_source"):
        load_gold_pairs(_write(tmp_path, [_grow(dataset_source="my_laptop")]))


# ── 8. duplicate pair_id 거부 ────────────────────────────────────────────────────────
def test_duplicate_pair_id_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate pair_id"):
        load_gold_pairs(_write(tmp_path, [_grow(pair_id="dup"), _grow(pair_id="dup")]))


# ── 9·10. raw body / PII / 워크시트 보조키 거부(allowlist) ────────────────────────────
def test_raw_body_field_rejected(tmp_path):
    row = _grow(); row["body"] = "full article text never stored"
    with pytest.raises(ValueError, match="disallowed keys"):
        load_gold_pairs(_write(tmp_path, [row]))


def test_pii_like_field_rejected(tmp_path):
    for pii in ("author", "email", "phone", "content", "raw_text"):
        row = _grow(); row[pii] = "x"
        with pytest.raises(ValueError, match="disallowed keys"):
            load_gold_pairs(_write(tmp_path, [row]))


def test_worksheet_aux_key_leak_rejected(tmp_path):
    # 승격 시 제거돼야 할 워크시트 보조키(predicted_status/score/reason)가 gold 에 남으면 거부.
    for aux in ("predicted_status", "score", "reason"):
        row = _grow(); row[aux] = "leak"
        with pytest.raises(ValueError, match="disallowed keys"):
            load_gold_pairs(_write(tmp_path, [row]))


def test_oversized_title_rejected(tmp_path):
    with pytest.raises(ValueError, match="전문 위장 차단|≤"):
        load_gold_pairs(_write(tmp_path, [_grow(title_left="A" * 5000)]))


# ── 11·12. needs_review/rejected 는 gold metric 에서 제외 ─────────────────────────────
def test_needs_review_excluded_from_gold_metrics():
    pairs = load_gold_pairs(_GOLD_FIXTURE)
    on_gold = evaluate_adjudicator_on_gold(pairs)["overall"]["count"]
    gold_only = sum(1 for p in pairs if p.review_status == "gold")
    assert on_gold == gold_only
    assert any(p.review_status == "needs_review" for p in pairs)   # 샘플에 존재하나 metric 제외


def test_rejected_excluded_from_gold_metrics():
    pairs = load_gold_pairs(_GOLD_FIXTURE)
    assert any(p.review_status == "rejected" for p in pairs)
    # rejected 행을 추가해도 metric count 불변(제외).
    on_gold = evaluate_adjudicator_on_gold(pairs)["overall"]["count"]
    extra = pairs + [GoldPair(
        pair_id="rj_extra", label="same_event", language="en",
        source_type_left="article", source_type_right="article",
        title_left="x y z", title_right="x y z",
        observed_at_left="2026-06-24T09:00:00Z", observed_at_right="2026-06-24T09:00:00Z",
        reviewed_by="r", reviewed_at="2026-06-24T18:00:00Z",
        review_status="rejected", label_confidence="low", dataset_source=SOURCE_LIVE,
    )]
    assert evaluate_adjudicator_on_gold(extra)["overall"]["count"] == on_gold


# ── 13·15·17. 워크시트→gold 라운드트립·결정론·marker 보존 ────────────────────────────
def test_worksheet_to_gold_promotion_roundtrip(tmp_path):
    worksheet_row = {
        "pair_id": "l42", "label": "unlabeled", "language": "ko",
        "source_type_left": "article", "source_type_right": "official",
        "title_left": "코스피 서킷브레이커 발동 증시 급락 오늘",
        "title_right": "코스피 서킷브레이커 발동 증시 급락",
        "observed_at_left": "2026-06-24T04:00:00Z", "observed_at_right": "2026-06-24T05:00:00Z",
        "predicted_status": "likely_same_event", "score": 0.9, "reason": "high_sim_near_date", "risk_tags": [],
    }
    gold = promote_worksheet_to_gold(
        worksheet_row, label="same_event", reviewed_by="sample_reviewer",
        reviewed_at="2026-06-24T18:00:00Z", review_status="gold", label_confidence="high",
        dataset_source=SOURCE_LIVE, rationale="reviewer confirmed same halt event",
    )
    assert "predicted_status" not in gold and "score" not in gold and "reason" not in gold
    p = tmp_path / "promoted.jsonl"
    n = write_gold_jsonl([gold], p)
    assert n == 1
    loaded = load_gold_pairs(p)
    assert len(loaded) == 1
    gp = loaded[0]
    assert gp.label == "same_event" and gp.review_status == "gold"
    assert gp.dataset_source == SOURCE_LIVE           # live-derived marker 보존
    # 결정론: 같은 입력 → 같은 파일.
    t1 = p.read_text(encoding="utf-8")
    write_gold_jsonl([gold], p)
    assert t1 == p.read_text(encoding="utf-8")


def test_write_gold_jsonl_validates_before_write(tmp_path):
    # 부적합 행(보조키 누출)은 기록 전 거부 — dead-data 방지.
    bad = _grow(); bad["predicted_status"] = "leak"
    with pytest.raises(ValueError, match="disallowed keys"):
        write_gold_jsonl([bad], tmp_path / "x.jsonl")


# ── 14. gold → metrics report ────────────────────────────────────────────────────────
def test_generate_gold_eval_report_shape():
    rep = generate_gold_eval_report(load_gold_pairs(_GOLD_FIXTURE), total_exported=20)
    for k in ("gold_precision", "gold_fpr", "gold_recall", "gold_coverage",
              "gold_ambiguous_rate", "gold_insufficient_rate", "gold_hard_negative_fp",
              "gold_by_language", "gold_by_source_type", "gold_by_risk_tag",
              "merge_readiness", "backlog", "dataset_sources_present"):
        assert k in rep
    assert rep["auto_merged"] == 0
    assert rep["backlog"]["total_exported"] == 20


# ── 16. fixture/gold 분리 — synthetic 은 readiness 표본/precision 에 산입 안 됨 ───────
def test_fixture_and_gold_separation():
    pairs = load_gold_pairs(_GOLD_FIXTURE)
    # 샘플에 synthetic_fixture gold 행 존재.
    assert any(p.dataset_source == SOURCE_SYNTHETIC and p.review_status == "gold" for p in pairs)
    mr = evaluate_gold_merge_readiness(pairs)
    live_gold = sum(1 for p in pairs if p.review_status == "gold" and p.dataset_source == SOURCE_LIVE)
    assert mr["live_gold_count"] == live_gold       # synthetic 제외
    # 전체 gold count(synthetic 포함) > live_gold_count.
    all_gold = sum(1 for p in pairs if p.review_status == "gold")
    assert all_gold > live_gold


# ── 18·19·20·21. gold precision/FPR/recall/hard-neg FP 산출 ──────────────────────────
def test_gold_precision_fpr_recall_hardneg_computed():
    rep = generate_gold_eval_report(load_gold_pairs(_GOLD_FIXTURE))
    assert rep["gold_precision"] is not None and 0.0 <= rep["gold_precision"] <= 1.0
    assert rep["gold_fpr"] is not None and rep["gold_fpr"] > 0.0       # 템플릿 충돌 FP 존재
    assert rep["gold_recall"] is not None and rep["gold_recall"] < 1.0  # 패러프레이즈/번역 FN
    assert rep["gold_hard_negative_fp"] >= 1                            # korean+english hard-neg FP


# ── 22·23·24. by_language / by_source_type / by_risk_tag ─────────────────────────────
def test_gold_breakdowns_present():
    rep = generate_gold_eval_report(load_gold_pairs(_GOLD_FIXTURE))
    assert {"ko", "en", "mixed"} <= set(rep["gold_by_language"])
    assert any("community" in k for k in rep["gold_by_source_type"])
    assert "hard_negative" in rep["gold_by_risk_tag"]


# ── 25. fixture_vs_gold_delta 산출 ───────────────────────────────────────────────────
def test_fixture_vs_gold_delta_computed():
    cmp = compare_fixture_vs_gold_metrics(load_eval_pairs(_EVAL_FIXTURE), load_gold_pairs(_GOLD_FIXTURE))
    d = cmp["fixture_vs_gold_delta"]
    assert "likely_same_precision" in d and "same_event_recall" in d
    assert cmp["fixture"]["count"] > 0 and cmp["gold"]["count"] > 0
    # fixture 와 gold 는 따로 평가(섞지 않음) — 둘 다 산출.
    assert cmp["fixture"]["likely_same_precision"] is not None
    assert cmp["gold"]["likely_same_precision"] is not None


# ── 26·27. merge readiness 미충족·자동 병합 OFF(핵심 정직 계약) ──────────────────────
def test_merge_readiness_false_and_auto_merge_off():
    mr = evaluate_gold_merge_readiness(load_gold_pairs(_GOLD_FIXTURE))
    # 샘플은 표본 floor(200) 한참 미달 + precision 미달 → readiness False.
    assert mr["live_sample_ok"] is False
    assert mr["korean_sample_ok"] is False
    assert mr["passed"] is False                  # metric gate 미달
    assert mr["merge_ready"] is False
    # **불변**: readiness 와 무관하게 자동 병합은 절대 켜지지 않는다.
    assert mr["auto_merge_enabled"] is False


def test_merge_readiness_sample_floors_sane():
    # 표본 floor 는 의미 있는 통계 규모(샘플 13행으로 절대 충족 불가).
    assert GOLD_MERGE_MIN_LIVE_GOLD >= 100
    assert GOLD_MERGE_MIN_KOREAN_GOLD >= 20


def test_evaluate_deterministic():
    pairs = load_gold_pairs(_GOLD_FIXTURE)
    a = generate_gold_eval_report(pairs)
    b = generate_gold_eval_report(pairs)
    assert a == b


def test_no_pairs_safe():
    rep = generate_gold_eval_report([])
    assert rep["gold_count"] == 0 and rep["auto_merged"] == 0
    assert rep["merge_readiness"]["auto_merge_enabled"] is False


# ── 28·29. Korean subset / mixed subset metric ───────────────────────────────────────
def test_korean_subset_metric():
    rep = generate_gold_eval_report(load_gold_pairs(_GOLD_FIXTURE))
    ko = rep["gold_by_language"]["ko"]
    assert ko["count"] >= 3
    # 한국어에도 template 충돌 FP 가 있어 precision < 1.0(평균 뒤에 숨기지 않음).
    assert ko["likely_same_precision"] is not None and ko["likely_same_precision"] < 1.0


def test_mixed_subset_metric():
    rep = generate_gold_eval_report(load_gold_pairs(_GOLD_FIXTURE))
    assert "mixed" in rep["gold_by_language"]
    mixed = rep["gold_by_language"]["mixed"]
    assert mixed["count"] >= 1
    # mixed 번역쌍은 deterministic 층이 놓침(FN) → same_event_recall < 1.0.
    assert mixed["same_event_recall"] is not None and mixed["same_event_recall"] < 1.0


# ── 30·31·32. translation / paraphrase / korean hard-negative risk_tag metric ────────
def test_risk_tag_metrics_present():
    rep = generate_gold_eval_report(load_gold_pairs(_GOLD_FIXTURE))
    rt = rep["gold_by_risk_tag"]
    assert "translation" in rt and "paraphrase" in rt and "hard_negative" in rt
    # translation/paraphrase subset 은 FN 으로 recall < 1.0(놓침).
    assert rt["translation"]["same_event_recall"] is not None and rt["translation"]["same_event_recall"] < 1.0
    assert rt["paraphrase"]["same_event_recall"] is not None and rt["paraphrase"]["same_event_recall"] < 1.0
    # hard_negative subset 에서 FP 발생(현재 adjudicator 실패모드).
    assert rt["hard_negative"]["fp"] >= 1


def test_korean_hard_negative_present():
    pairs = load_gold_pairs(_GOLD_FIXTURE)
    ko_hard_neg = [p for p in pairs if p.language == "ko" and "hard_negative" in p.risk_tags
                   and p.review_status == "gold"]
    assert len(ko_hard_neg) >= 1                  # 한국어 hard-negative 가 gold 에 존재
    # 그 한국어 hard-negative 가 adjudicator FP 를 유발(같은 템플릿 → likely_same 오판).
    gp = ko_hard_neg[0]
    ep = gold_to_eval_pair(gp)
    from backend.app.services.identity_eval_dataset import predict_status, ADJ_LIKELY_SAME
    assert predict_status(ep) == ADJ_LIKELY_SAME and gp.label != "same_event"
