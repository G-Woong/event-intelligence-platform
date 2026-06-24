from __future__ import annotations

"""Reviewer agreement / resolution / sampling / sample-floor 단위 (ADR#45, R-IdentityHumanLabeling·R-ReviewerAgreement).

다중 reviewer 합의→gold·conflict→자동 gold 금지·single→insufficient·model/self label 거부·sampling bucket·
통계적 sample floor 추정·labeling protocol report 를 잠근다. 실 reviewer/운영 gold 는 아직 0(부분진전).
"""

import json
from pathlib import Path

import pytest

from backend.app.services.identity_human_labeling import (
    AGREE_ADJUDICATED,
    AGREE_AGREED,
    AGREE_CONFLICT,
    AGREE_INSUFFICIENT,
    GOLD_MERGE_MIN_LIVE_GOLD,
    REVIEW_GOLD,
    REVIEW_NEEDS,
    SAMPLING_MIN_TARGET_DRAFT,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    ReviewerLabel,
    assign_sampling_bucket,
    compute_reviewer_agreement,
    estimate_sample_floor_for_fpr,
    estimate_sample_floor_for_precision,
    generate_labeling_protocol_report,
    load_reviewer_labels,
    recommended_sample_floors,
    resolve_gold_from_reviewers,
    resolved_to_gold_pairs,
    summarize_sampling_buckets,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "identity_reviewer_labels.sample.jsonl"
_ADJ = {"adjud_en": {"label": "different_event", "adjudicated_by": "reviewer-lead"}}


def _rl(**kw):
    base = {
        "pair_id": "p1", "reviewer_id": "reviewer-a", "review_round": 1,
        "label": "same_event", "label_confidence": "high", "reviewed_at": "2026-06-24T18:00:00Z",
        "language": "en", "source_type_left": "article", "source_type_right": "article",
        "title_left": "Federal Reserve raises benchmark interest rates today",
        "title_right": "Federal Reserve raises benchmark interest rates today",
        "observed_at_left": "2026-06-24T09:00:00Z", "observed_at_right": "2026-06-24T10:00:00Z",
    }
    base.update(kw)
    return base


def _write(tmp_path, rows):
    p = tmp_path / "rev.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def _labels():
    return load_reviewer_labels(_FIXTURE)


# ── 1. valid reviewer label loads ────────────────────────────────────────────────────
def test_load_sample_reviewer_labels_ok():
    labs = _labels()
    assert len(labs) >= 14
    assert all(isinstance(x, ReviewerLabel) for x in labs)
    assert all(x.reviewer_kind == "human" for x in labs)


# ── 2·3. missing reviewer_id / review_round reject ───────────────────────────────────
def test_missing_reviewer_id_rejected(tmp_path):
    row = _rl(); del row["reviewer_id"]
    with pytest.raises(ValueError, match="missing required keys"):
        load_reviewer_labels(_write(tmp_path, [row]))


def test_missing_review_round_rejected(tmp_path):
    row = _rl(); del row["review_round"]
    with pytest.raises(ValueError, match="missing required keys"):
        load_reviewer_labels(_write(tmp_path, [row]))


def test_invalid_review_round_rejected(tmp_path):
    with pytest.raises(ValueError, match="review_round must be int"):
        load_reviewer_labels(_write(tmp_path, [_rl(review_round=0)]))


# ── 4·5·6. invalid label / confidence / reviewed_at reject ───────────────────────────
def test_invalid_label_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid label"):
        load_reviewer_labels(_write(tmp_path, [_rl(label="merge_now")]))


def test_invalid_confidence_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid label_confidence"):
        load_reviewer_labels(_write(tmp_path, [_rl(label_confidence="certain")]))


def test_invalid_reviewed_at_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid reviewed_at"):
        load_reviewer_labels(_write(tmp_path, [_rl(reviewed_at="today")]))


# ── 7·8. raw body / PII reject ───────────────────────────────────────────────────────
def test_raw_body_rejected(tmp_path):
    row = _rl(); row["body"] = "full text"
    with pytest.raises(ValueError, match="disallowed keys"):
        load_reviewer_labels(_write(tmp_path, [row]))


def test_pii_like_rejected(tmp_path):
    for pii in ("author", "email", "content", "raw_text"):
        row = _rl(); row[pii] = "x"
        with pytest.raises(ValueError, match="disallowed keys"):
            load_reviewer_labels(_write(tmp_path, [row]))


# ── 9. duplicate (pair, reviewer, round) reject ──────────────────────────────────────
def test_duplicate_reviewer_label_rejected(tmp_path):
    rows = [_rl(pair_id="d", reviewer_id="r1", review_round=1),
            _rl(pair_id="d", reviewer_id="r1", review_round=1)]
    with pytest.raises(ValueError, match="duplicate reviewer label"):
        load_reviewer_labels(_write(tmp_path, rows))


# ── 10. model/self label cannot be gold ──────────────────────────────────────────────
def test_model_self_label_rejected(tmp_path):
    for kind in ("model", "llm", "adjudicator", "self"):
        with pytest.raises(ValueError, match="cannot be gold|model/self label"):
            load_reviewer_labels(_write(tmp_path, [_rl(reviewer_kind=kind)]))


# ── 11·12·13·14. resolution: agree→gold·conflict→no auto gold·adjudicated→gold·single→insuf
def test_resolution_statuses():
    res = {r.pair_id: r for r in resolve_gold_from_reviewers(_labels(), adjudications=_ADJ)}
    assert res["agree_en_same"].agreement_status == AGREE_AGREED
    assert res["agree_en_same"].review_status == REVIEW_GOLD
    assert res["conflict_en"].agreement_status == AGREE_CONFLICT
    assert res["conflict_en"].review_status == REVIEW_NEEDS      # **자동 gold 금지**
    assert res["conflict_en"].label is None                      # 단일 gold label 없음
    assert res["adjud_en"].agreement_status == AGREE_ADJUDICATED
    assert res["adjud_en"].review_status == REVIEW_GOLD
    assert res["adjud_en"].label == "different_event"            # adjudication label
    assert res["adjud_en"].adjudicated_by == "reviewer-lead"
    assert res["single_en"].agreement_status == AGREE_INSUFFICIENT
    assert res["single_en"].review_status == REVIEW_NEEDS        # 단일 reviewer → provisional


def test_conflict_and_single_excluded_from_gold():
    res = resolve_gold_from_reviewers(_labels(), adjudications=_ADJ)
    gold = resolved_to_gold_pairs(res)
    gold_ids = {g.pair_id for g in gold}
    assert "conflict_en" not in gold_ids and "single_en" not in gold_ids   # gold 제외
    assert "agree_en_same" in gold_ids and "adjud_en" in gold_ids


def test_adjudication_absent_keeps_conflict():
    # adjudication 없이 conflict → 여전히 conflict(자동 gold 금지).
    res = {r.pair_id: r for r in resolve_gold_from_reviewers(_labels(), adjudications=None)}
    assert res["adjud_en"].agreement_status == AGREE_CONFLICT
    assert res["adjud_en"].review_status == REVIEW_NEEDS


def test_model_adjudicator_rejected():
    # adversarial Q3: LLM-as-judge 가 adjudication 경로로 gold 를 만드는 뒷문 봉인(fail-loud).
    for bad in (
        {"adjud_en": {"label": "different_event", "adjudicated_by": "gpt-4", "adjudicator_kind": "model"}},
        {"adjud_en": {"label": "different_event", "adjudicated_by": "llm-judge", "adjudicator_kind": "llm"}},
        {"adjud_en": {"label": "different_event", "adjudicated_by": ""}},          # 빈 adjudicated_by
        {"adjud_en": {"label": "different_event"}},                                # adjudicated_by 누락
    ):
        with pytest.raises(ValueError, match="LLM-as-judge 금지|adjudicated_by required"):
            resolve_gold_from_reviewers(_labels(), adjudications=bad)


def test_human_adjudicator_accepted():
    # 사람 adjudicator(adjudicator_kind 기본 human)는 정상 — conflict 해소 → adjudicated gold.
    res = {r.pair_id: r for r in resolve_gold_from_reviewers(
        _labels(), adjudications={"adjud_en": {"label": "different_event", "adjudicated_by": "lead", "adjudicator_kind": "human"}})}
    assert res["adjud_en"].agreement_status == AGREE_ADJUDICATED


# ── 15·16·17·18. agreement rate / conflict count / reviewer count / resolution method ─
def test_agreement_metrics():
    ag = compute_reviewer_agreement(_labels())
    assert ag["multi_reviewer_pairs"] >= 6
    assert ag["agreement_rate"] is not None and 0.0 < ag["agreement_rate"] < 1.0   # 일부 conflict
    rep = generate_labeling_protocol_report(_labels(), adjudications=_ADJ)
    assert rep["conflict_count"] == 1
    assert rep["insufficient_reviews_count"] == 1
    # 정확 등식(회귀 민감도): agreed 5(en_same/ko_diff/mixed_translation/community/multiround)·adjudicated 1.
    assert rep["agreed_count"] == 5 and rep["adjudicated_count"] == 1


def test_reviewer_count_and_resolution_method():
    res = {r.pair_id: r for r in resolve_gold_from_reviewers(_labels(), adjudications=_ADJ)}
    assert res["single_en"].reviewer_count == 1
    assert res["agree_en_same"].reviewer_count == 2
    assert res["agree_en_same"].resolution_method == "agreement"
    assert res["adjud_en"].resolution_method == "adjudicated"
    assert res["single_en"].resolution_method == "single_reviewer"


# ── 19. live vs synthetic preserved ──────────────────────────────────────────────────
def test_dataset_source_preserved(tmp_path):
    rows = [_rl(pair_id="s", reviewer_id="r1", dataset_source=SOURCE_SYNTHETIC),
            _rl(pair_id="s", reviewer_id="r2", dataset_source=SOURCE_SYNTHETIC)]
    res = resolve_gold_from_reviewers(load_reviewer_labels(_write(tmp_path, rows)))
    assert res[0].dataset_source == SOURCE_SYNTHETIC


# ── 20. multi-round: 같은 reviewer 최신 round 적용 ───────────────────────────────────
def test_latest_round_wins():
    # multiround_en: reviewer-a r1=different, r2=same; reviewer-b=same → 최신(a=same,b=same)=agreed.
    res = {r.pair_id: r for r in resolve_gold_from_reviewers(_labels())}
    assert res["multiround_en"].agreement_status == AGREE_AGREED
    assert res["multiround_en"].label == "same_event"


# ── 21~26. sampling bucket assignment ────────────────────────────────────────────────
def test_bucket_assignment_rules():
    assert assign_sampling_bucket(language="en", source_type_left="article", source_type_right="article",
                                  label="different_event", risk_tags=("hard_negative",)) == "likely_same_hard_negative"
    assert assign_sampling_bucket(language="ko", source_type_left="article", source_type_right="article",
                                  label="same_event", risk_tags=()) == "ko_same_event"
    assert assign_sampling_bucket(language="mixed", source_type_left="article", source_type_right="article",
                                  label="same_event", risk_tags=("translation",)) == "mixed_translation"
    assert assign_sampling_bucket(language="en", source_type_left="community", source_type_right="community",
                                  label="insufficient", risk_tags=()) == "community_only"
    assert assign_sampling_bucket(language="en", source_type_left="catalog", source_type_right="catalog",
                                  label="insufficient", risk_tags=()) == "catalog_only"
    assert assign_sampling_bucket(language="en", source_type_left="article", source_type_right="article",
                                  label="different_event", risk_tags=("far_date",)) == "far_date_same_title"
    # adversarial Q6: 태그 없는 publishable insufficient 도 other 가 아니라 insufficient bucket 으로(커버리지 공백 차단).
    assert assign_sampling_bucket(language="en", source_type_left="article", source_type_right="article",
                                  label="insufficient", risk_tags=()) == "insufficient_generic"


def test_sampling_summary_buckets_and_warning():
    res = resolve_gold_from_reviewers(_labels(), adjudications=_ADJ)
    s = summarize_sampling_buckets(res)
    assert "by_bucket" in s and s["unclassified"] == 0          # 전부 분류됨(조용한 누락 0)
    # 작은 샘플 → 모든 bucket 이 draft target 미달(대표성 경고).
    assert len(s["under_filled_buckets"]) >= 1
    assert s["min_target_draft"] == SAMPLING_MIN_TARGET_DRAFT


def test_conflict_label_none_excluded_from_buckets():
    # conflict(label=None)은 bucket 분류에서 제외(잘못 분류 금지).
    res = resolve_gold_from_reviewers(_labels(), adjudications=None)
    s = summarize_sampling_buckets(res)
    total_classified = sum(s["by_bucket"].values())
    non_conflict = sum(1 for r in res if r.label is not None)
    assert total_classified == non_conflict


# ── 27. labeling protocol report deterministic ───────────────────────────────────────
def test_protocol_report_deterministic():
    a = generate_labeling_protocol_report(_labels(), total_exported=20, adjudications=_ADJ)
    b = generate_labeling_protocol_report(_labels(), total_exported=20, adjudications=_ADJ)
    assert a == b
    assert a["total_pairs_exported"] == 20 and a["auto_merged"] == 0


# ── 28·29·30. sample floor estimators (통계 근거) ────────────────────────────────────
def test_sample_floor_precision_estimate():
    # precision 0.98·±0.02·95% → ~189 (normal-approx). 200 placeholder 와 같은 자릿수.
    n = estimate_sample_floor_for_precision(0.98, 0.02)
    assert 150 <= n <= 230


def test_sample_floor_fpr_estimate():
    # FPR 0.01·±0.01·95% → ~381. 음성 floor 가 양성보다 큼(hard-negative oversample 필요).
    n = estimate_sample_floor_for_fpr(0.01, 0.01)
    assert n > estimate_sample_floor_for_precision(0.98, 0.02)


def test_recommended_floors_flag_draft_as_optimistic():
    r = recommended_sample_floors()
    assert r["draft_live_gold_floor"] == GOLD_MERGE_MIN_LIVE_GOLD
    assert r["recommended_negative_floor"] > r["draft_korean_gold_floor"]   # KO 50 은 낙관적
    assert "placeholder" in r["note"]


# ── 31·32. merge readiness still False·auto-merge OFF (gold from reviewers) ───────────
def test_protocol_merge_readiness_false_and_auto_merge_off():
    rep = generate_labeling_protocol_report(_labels(), adjudications=_ADJ)
    gm = rep["gold_metrics"]
    assert gm is not None and gm["gold_count"] >= 1
    mr = gm["merge_readiness"]
    assert mr["live_sample_ok"] is False           # 6 gold << floor 200
    assert mr["merge_ready"] is False and mr["auto_merge_enabled"] is False


def test_protocol_gold_precision_honest():
    # reviewer 합의 gold 라도 현재 deterministic adjudicator precision < 0.98(병합 미달 — 정직).
    rep = generate_labeling_protocol_report(_labels(), adjudications=_ADJ)
    gm = rep["gold_metrics"]
    assert gm["gold_precision"] is not None and gm["gold_precision"] < 0.98


# ── 33. regression: 기존 ADR#44 gold workflow 유지 ───────────────────────────────────
def test_adr44_gold_workflow_intact():
    from backend.app.services.identity_human_labeling import load_gold_pairs, generate_gold_eval_report
    gold_fx = Path(__file__).resolve().parent / "fixtures" / "identity_gold_pairs.sample.jsonl"
    rep = generate_gold_eval_report(load_gold_pairs(gold_fx))
    assert rep["merge_readiness"]["auto_merge_enabled"] is False    # ADR#44 불변 회귀 0
