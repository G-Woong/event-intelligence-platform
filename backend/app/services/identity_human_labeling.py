"""Human-labeled gold workflow + gold metric harness (ADR#44, R-IdentityHumanLabeling).

ADR#43 `export_identity_eval_pairs` 는 adjudication → **워크시트 JSONL**(label='unlabeled')만 만든다.
사람이 그 워크시트에 gold label 을 달아 **gold set** 으로 승격하는 경로(provenance 검증·gold-only metric)는
없었다 → 워크시트가 또 다른 휘발성 산출물(dead-data 형태 변환). 이 모듈이 그 마지막 한 단계를 채운다:

  - **gold schema**: EvalPair(ADR#43) + provenance(reviewed_by·reviewed_at·review_status·label_confidence) +
    `dataset_source`(synthetic_fixture | live_derived) 분리자. raw body/PII 는 allowlist 로 구조적 차단(상속).
  - **load_gold_pairs**: gold JSONL 로드·검증(provenance 필수·enum·reviewed_at ISO·중복·전문 위장 차단).
  - **promote_worksheet_to_gold**: 워크시트 행 + 사람 결정 → gold 행(보조키 제거·provenance 부여) — 라운드트립.
  - **evaluate_adjudicator_on_gold**: review_status='gold' 만 골라 현재 adjudicator 평가(ADR#43 harness 재사용).
  - **compare_fixture_vs_gold_metrics** / **generate_gold_eval_report** / **summarize_labeling_backlog**.
  - **evaluate_gold_merge_readiness**: MERGE_GATE(ADR#43) + **live-derived gold 표본 floor** = report condition.
    **자동 병합은 절대 켜지 않는다**(auto_merge_enabled=False 불변; 런타임 merge 배선 없음).

옵션 A(JSONL roundtrip) 채택 — 옵션 B(DB labeling queue)=roadmap future·옵션 C(LLM self-label)=gold 금지.
DB/migration 없음·결정론(LLM/network 0)·stdlib + ADR#43 harness pure 재사용.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.app.services.identity_eval_dataset import (
    ALLOWED_KEYS,
    GOLD_LABELS,
    LABEL_AMBIGUOUS,
    LABEL_DIFFERENT,
    LABEL_INSUFFICIENT,
    LABEL_SAME,
    LANGUAGES,
    SOURCE_TYPES,
    EvalPair,
    _MAX_TITLE_LEN,
    evaluate_adjudicator,
    evaluate_merge_gate,
)

# review_status — 사람 검수 결과(gold 만 metric 에 산입; needs_review/rejected 는 제외·별도 카운트).
REVIEW_GOLD = "gold"
REVIEW_NEEDS = "needs_review"
REVIEW_REJECTED = "rejected"
REVIEW_STATUSES = frozenset({REVIEW_GOLD, REVIEW_NEEDS, REVIEW_REJECTED})

LABEL_CONFIDENCES = frozenset({"high", "medium", "low"})

# dataset_source — synthetic fixture(진단·대표성 0) 와 live-derived(human-reviewed) gold 를 **구분**.
# merge readiness 표본 floor 는 live_derived gold 만 센다(synthetic 으로 gate 충족 금지).
SOURCE_SYNTHETIC = "synthetic_fixture"
SOURCE_LIVE = "live_derived"
DATASET_SOURCES = frozenset({SOURCE_SYNTHETIC, SOURCE_LIVE})

# gold 행 허용 키 = eval 키(ADR#43 allowlist) + provenance + dataset_source. predicted_status/score/reason 등
# 워크시트 보조키나 body/raw_text/author/email 은 구조적 차단(raw≠gold, PII 차단). 승격 시 보조키 제거 강제.
_PROVENANCE_KEYS = frozenset({"reviewed_by", "reviewed_at", "review_status", "label_confidence"})
GOLD_ALLOWED_KEYS = ALLOWED_KEYS | _PROVENANCE_KEYS | {"dataset_source"}
_GOLD_REQUIRED_KEYS = frozenset({
    "pair_id", "label", "language", "source_type_left", "source_type_right",
    "title_left", "title_right", "observed_at_left", "observed_at_right",
}) | _PROVENANCE_KEYS

# 워크시트→gold 승격 시 반드시 제거돼야 할 보조키(gold 에 새 들어오면 거부).
_WORKSHEET_AUX_KEYS = frozenset({"predicted_status", "score", "reason"})

# ── gold merge readiness 표본 floor 초안(ADR#44 §5) — **report 전용·운영 합의 전 초안**. ──
# 충족돼도 자동 병합 OFF(런타임 배선 없음). 통계 규모/한국어 대표성을 평균 precision 뒤에 숨기지 않기 위함.
GOLD_MERGE_MIN_LIVE_GOLD = 200      # live-derived gold(review_status='gold') 최소 표본
GOLD_MERGE_MIN_KOREAN_GOLD = 50     # 한국어 gold 최소 표본(한국어 캘리브레이션 floor)


@dataclass(frozen=True)
class GoldPair:
    pair_id: str
    label: str
    language: str
    source_type_left: str
    source_type_right: str
    title_left: str
    title_right: str
    observed_at_left: str
    observed_at_right: str
    reviewed_by: str
    reviewed_at: str
    review_status: str
    label_confidence: str
    dataset_source: str = SOURCE_LIVE
    canonical_url_left: Optional[str] = None
    canonical_url_right: Optional[str] = None
    rationale: Optional[str] = None
    risk_tags: tuple[str, ...] = ()


def _validate_reviewed_at(raw: Any) -> None:
    s = (raw or "").strip() if isinstance(raw, str) else ""
    if not s:
        raise ValueError("reviewed_at required (provenance) — non-empty ISO8601")
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid reviewed_at {raw!r} (ISO8601 required): {exc}") from exc


def _validate_gold_row(row: dict, *, seen_ids: set[str]) -> None:
    keys = set(row)
    extra = keys - GOLD_ALLOWED_KEYS
    if extra:
        # 워크시트 보조키 누출도 여기서 잡힌다(predicted_status/score/reason ⊄ GOLD_ALLOWED_KEYS).
        raise ValueError(f"gold row has disallowed keys (raw body/PII/worksheet aux 차단): {sorted(extra)}")
    missing = _GOLD_REQUIRED_KEYS - keys
    if missing:
        raise ValueError(f"gold row missing required keys (provenance 포함): {sorted(missing)}")
    pid = row["pair_id"]
    if pid in seen_ids:
        raise ValueError(f"duplicate pair_id: {pid}")
    seen_ids.add(pid)
    if row["label"] not in GOLD_LABELS:
        raise ValueError(f"invalid label {row['label']!r} (allowed: {sorted(GOLD_LABELS)})")
    if row["language"] not in LANGUAGES:
        raise ValueError(f"invalid language {row['language']!r}")
    for side in ("source_type_left", "source_type_right"):
        if row[side] not in SOURCE_TYPES:
            raise ValueError(f"invalid {side} {row[side]!r}")
    for side in ("title_left", "title_right"):
        if not isinstance(row[side], str) or len(row[side]) > _MAX_TITLE_LEN:
            raise ValueError(f"{side} must be str ≤ {_MAX_TITLE_LEN} chars (전문 위장 차단)")
    if row["review_status"] not in REVIEW_STATUSES:
        raise ValueError(f"invalid review_status {row['review_status']!r} (allowed: {sorted(REVIEW_STATUSES)})")
    if row["label_confidence"] not in LABEL_CONFIDENCES:
        raise ValueError(f"invalid label_confidence {row['label_confidence']!r}")
    if not isinstance(row["reviewed_by"], str) or not row["reviewed_by"].strip():
        raise ValueError("reviewed_by required (provenance) — non-empty str")
    _validate_reviewed_at(row["reviewed_at"])
    ds = row.get("dataset_source", SOURCE_LIVE)
    if ds not in DATASET_SOURCES:
        raise ValueError(f"invalid dataset_source {ds!r} (allowed: {sorted(DATASET_SOURCES)})")
    rt = row.get("risk_tags", [])
    if not isinstance(rt, list) or any(not isinstance(t, str) for t in rt):
        raise ValueError("risk_tags must be a list of str")


def load_gold_pairs(path: Any) -> list[GoldPair]:
    """human-labeled gold JSONL 로드·검증. provenance 필수·enum·reviewed_at ISO·중복·전문/PII 차단."""
    seen: set[str] = set()
    pairs: list[GoldPair] = []
    text = Path(path).read_text(encoding="utf-8")
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"gold pair line {ln} invalid JSON: {exc}") from exc
        _validate_gold_row(row, seen_ids=seen)
        pairs.append(GoldPair(
            pair_id=row["pair_id"], label=row["label"], language=row["language"],
            source_type_left=row["source_type_left"], source_type_right=row["source_type_right"],
            title_left=row["title_left"], title_right=row["title_right"],
            observed_at_left=row["observed_at_left"], observed_at_right=row["observed_at_right"],
            reviewed_by=row["reviewed_by"], reviewed_at=row["reviewed_at"],
            review_status=row["review_status"], label_confidence=row["label_confidence"],
            dataset_source=row.get("dataset_source", SOURCE_LIVE),
            canonical_url_left=row.get("canonical_url_left"),
            canonical_url_right=row.get("canonical_url_right"),
            rationale=row.get("rationale"),
            risk_tags=tuple(row.get("risk_tags", [])),
        ))
    return pairs


def promote_worksheet_to_gold(
    worksheet_row: dict,
    *,
    label: str,
    reviewed_by: str,
    reviewed_at: str,
    review_status: str = REVIEW_GOLD,
    label_confidence: str = "high",
    dataset_source: str = SOURCE_LIVE,
    rationale: Optional[str] = None,
) -> dict:
    """워크시트 행 + 사람 결정 → gold 행 dict(보조키 제거·provenance 부여). 검증은 load_gold_pairs 가 담당.

    워크시트의 predicted_status/score/reason 보조키는 제거(gold ⊄ 보조키). label='unlabeled' 를 사람이 정한
    gold label 로 교체. **자동 판단 아님** — 사람이 label/confidence/status 를 결정해 넘긴다(self-label 금지)."""
    gold = {k: v for k, v in worksheet_row.items() if k not in _WORKSHEET_AUX_KEYS}
    gold["label"] = label
    gold["reviewed_by"] = reviewed_by
    gold["reviewed_at"] = reviewed_at
    gold["review_status"] = review_status
    gold["label_confidence"] = label_confidence
    gold["dataset_source"] = dataset_source
    if rationale is not None:
        gold["rationale"] = rationale
    return gold


def write_gold_jsonl(rows: list[dict], path: Any) -> int:
    """gold 행 → JSONL(결정론·sort_keys). 기록 전 검증(provenance/allowlist) — 부적합 행이면 raise."""
    seen: set[str] = set()
    for r in rows:
        _validate_gold_row(r, seen_ids=seen)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(rows)


def gold_to_eval_pair(gp: GoldPair) -> EvalPair:
    """GoldPair → EvalPair(provenance 제거) — ADR#43 adjudicator 평가 입력으로 재사용."""
    return EvalPair(
        pair_id=gp.pair_id, label=gp.label, language=gp.language,
        source_type_left=gp.source_type_left, source_type_right=gp.source_type_right,
        title_left=gp.title_left, title_right=gp.title_right,
        observed_at_left=gp.observed_at_left, observed_at_right=gp.observed_at_right,
        canonical_url_left=gp.canonical_url_left, canonical_url_right=gp.canonical_url_right,
        rationale=gp.rationale, risk_tags=gp.risk_tags,
    )


def _gold_only(pairs: list[GoldPair]) -> list[GoldPair]:
    """metric 산입 대상 = review_status='gold' 만(needs_review/rejected 제외)."""
    return [p for p in pairs if p.review_status == REVIEW_GOLD]


def evaluate_adjudicator_on_gold(pairs: list[GoldPair]) -> dict:
    """review_status='gold' subset 에 현재 adjudicator 적용 → ADR#43 evaluate_adjudicator 와 동일 shape."""
    eval_pairs = [gold_to_eval_pair(p) for p in _gold_only(pairs)]
    return evaluate_adjudicator(eval_pairs)


def summarize_labeling_backlog(pairs: list[GoldPair], *, total_exported: Optional[int] = None) -> dict:
    """gold 파일 backlog 분포(by_status/language/source_type/risk_tag) — internal 모니터링.

    total_exported(워크시트 행 수)를 주면 labeling 진척률 분모로 함께 보고."""
    by_status: dict[str, int] = {s: 0 for s in (REVIEW_GOLD, REVIEW_NEEDS, REVIEW_REJECTED)}
    by_language: dict[str, int] = {}
    by_source_type: dict[str, int] = {}
    by_risk_tag: dict[str, int] = {}
    for p in pairs:
        by_status[p.review_status] = by_status.get(p.review_status, 0) + 1
        by_language[p.language] = by_language.get(p.language, 0) + 1
        key = "|".join(sorted((p.source_type_left, p.source_type_right)))
        by_source_type[key] = by_source_type.get(key, 0) + 1
        for t in p.risk_tags:
            by_risk_tag[t] = by_risk_tag.get(t, 0) + 1
    return {
        "total": len(pairs),
        "total_exported": total_exported,
        "labeled_gold": by_status[REVIEW_GOLD],
        "needs_review": by_status[REVIEW_NEEDS],
        "rejected": by_status[REVIEW_REJECTED],
        "by_status": by_status,
        "by_language": by_language,
        "by_source_type": by_source_type,
        "by_risk_tag": by_risk_tag,
        "auto_merged": 0,
    }


def evaluate_gold_merge_readiness(pairs: list[GoldPair]) -> dict:
    """**live-derived** gold-only metric + 표본 floor → merge readiness(**report 전용**).

    readiness 는 **live_derived gold(review_status='gold')만**으로 판정한다 — synthetic_fixture 는 precision·
    표본 어느 쪽도 부풀리지 못한다(진단 세트로 gate 통과 금지). MERGE_GATE(precision≥0.98·FPR≤0.01·hard-neg
    FP=0·KO subset, ADR#43) + 표본 floor(live gold·KO gold). **auto_merge_enabled=False 불변**(런타임 배선 없음)."""
    live_gold_pairs = [p for p in _gold_only(pairs) if p.dataset_source == SOURCE_LIVE]
    metrics = evaluate_adjudicator([gold_to_eval_pair(p) for p in live_gold_pairs])
    overall = metrics["overall"]
    korean = metrics["by_language"].get("ko", {})
    gate = evaluate_merge_gate(
        overall, korean=korean, hard_negative_fp=metrics["hard_negative_false_positive"]
    )
    live_gold = len(live_gold_pairs)
    korean_gold = sum(1 for p in live_gold_pairs if p.language == "ko")
    sample_checks = {
        "live_sample_ok": live_gold >= GOLD_MERGE_MIN_LIVE_GOLD,
        "korean_sample_ok": korean_gold >= GOLD_MERGE_MIN_KOREAN_GOLD,
    }
    return {
        **gate,                       # precision_ok/fpr_ok/hard_negative_fp_ok/korean_precision_ok/passed
        **sample_checks,
        "live_gold_count": live_gold,
        "korean_gold_count": korean_gold,
        "min_live_gold": GOLD_MERGE_MIN_LIVE_GOLD,
        "min_korean_gold": GOLD_MERGE_MIN_KOREAN_GOLD,
        # report 전용 종합: gate(metric) AND 표본 floor 모두 충족해야 readiness. 그래도 자동 병합은 OFF.
        "merge_ready": bool(gate["passed"] and sample_checks["live_sample_ok"] and sample_checks["korean_sample_ok"]),
        "auto_merge_enabled": False,  # 불변 — readiness 와 무관하게 production 자동 병합 금지.
    }


def generate_gold_eval_report(pairs: list[GoldPair], *, total_exported: Optional[int] = None) -> dict:
    """gold set 종합 평가 report — gold_* metric + breakdown + merge readiness + backlog. 자동 병합 0."""
    metrics = evaluate_adjudicator_on_gold(pairs)
    o = metrics["overall"]
    backlog = summarize_labeling_backlog(pairs, total_exported=total_exported)
    readiness = evaluate_gold_merge_readiness(pairs)
    by_source = {p.dataset_source for p in _gold_only(pairs)}
    return {
        "gold_count": o["count"],
        "gold_precision": o["likely_same_precision"],
        "gold_fpr": o["likely_same_false_positive_rate"],
        "gold_recall": o["same_event_recall"],
        "gold_coverage": o["coverage"],
        "gold_ambiguous_rate": o["ambiguous_rate"],
        "gold_insufficient_rate": o["insufficient_rate"],
        "gold_hard_negative_fp": metrics["hard_negative_false_positive"],
        "gold_by_language": metrics["by_language"],
        "gold_by_source_type": metrics["by_source_type"],
        "gold_by_risk_tag": metrics["by_risk_tag"],
        "dataset_sources_present": sorted(by_source),
        "backlog": backlog,
        "merge_readiness": readiness,
        "auto_merged": 0,
    }


def compare_fixture_vs_gold_metrics(fixture_pairs: list[EvalPair], gold_pairs: list[GoldPair]) -> dict:
    """진단 fixture(EvalPair) vs human-labeled gold(GoldPair) metric 비교 — delta 로 표본 차이 가시화.

    fixture(진단·대표성 0)와 gold(live+human)를 **섞지 않고** 따로 평가해 precision/FPR/recall delta 산출.
    delta = gold − fixture(둘 다 산출된 경우만; None 이면 None)."""
    fixture = evaluate_adjudicator(fixture_pairs)["overall"]
    gold = evaluate_adjudicator_on_gold(gold_pairs)["overall"]

    def _delta(key: str) -> Optional[float]:
        a, b = gold.get(key), fixture.get(key)
        return round(a - b, 4) if (a is not None and b is not None) else None

    return {
        "fixture": fixture,
        "gold": gold,
        "fixture_vs_gold_delta": {
            "likely_same_precision": _delta("likely_same_precision"),
            "likely_same_false_positive_rate": _delta("likely_same_false_positive_rate"),
            "same_event_recall": _delta("same_event_recall"),
            "coverage": _delta("coverage"),
        },
    }


# ════════════════════════════════════════════════════════════════════════════════════
# ADR#45 — production labeling protocol: reviewer agreement + sampling + sample-floor
# ════════════════════════════════════════════════════════════════════════════════════
# ADR#44 gold workflow 는 **단일 reviewer 의 label 을 곧장 gold** 로 취급했다(reviewed_by 하나·검증 없음).
# 상용 gold 는 (1) 다중 reviewer 합의(또는 adjudication)로 신뢰를 얻고, (2) conflict 를 자동 gold 로 올리지 않으며,
# (3) model/self label 을 gold 로 쓰지 않고, (4) sampling bucket 으로 대표성을 추적해야 한다. 이 계층이 그 운영
# protocol scaffold 다 — **실 reviewer/운영 gold 는 아직 0**(R-IdentityHumanLabeling 부분진전·R-ReviewerAgreement
# ·R-GoldSamplingBias). DB/migration 없음(JSONL)·결정론·자동 병합 0.

# reviewer 종류 — gold 는 **사람** 검수만. model/llm/adjudicator/self label 은 gold 금지(weak label 만 future).
REVIEWER_HUMAN = "human"
_MODEL_REVIEWER_KINDS = frozenset({"model", "llm", "adjudicator", "self", "heuristic"})
REVIEWER_KINDS = frozenset({REVIEWER_HUMAN}) | _MODEL_REVIEWER_KINDS

# 합의 상태 — 다중 reviewer label 의 resolution 결과.
AGREE_AGREED = "agreed"                # 2+ reviewer 전원 동일 label → gold
AGREE_CONFLICT = "conflict"            # 2+ reviewer 불일치·미adjudication → **gold 아님**(needs_review)
AGREE_ADJUDICATED = "adjudicated"      # conflict 를 lead 가 판정 → gold
AGREE_INSUFFICIENT = "insufficient_reviews"   # reviewer 1명 → provisional(gold 아님)
AGREEMENT_STATUSES = frozenset({AGREE_AGREED, AGREE_CONFLICT, AGREE_ADJUDICATED, AGREE_INSUFFICIENT})

RESOLUTION_SINGLE = "single_reviewer"
RESOLUTION_AGREEMENT = "agreement"
RESOLUTION_ADJUDICATED = "adjudicated"
RESOLUTION_NONE = "none"               # conflict 미해결 → resolution 없음(gold 승격 금지)

# reviewer label JSONL 허용 키 — eval 키 + reviewer provenance. raw body/PII/워크시트 보조키 구조적 차단.
_REVIEWER_PROVENANCE_KEYS = frozenset({"reviewer_id", "review_round", "label_confidence", "reviewed_at", "reviewer_kind"})
REVIEWER_ALLOWED_KEYS = (
    frozenset({"pair_id", "label", "language", "source_type_left", "source_type_right",
               "title_left", "title_right", "observed_at_left", "observed_at_right",
               "canonical_url_left", "canonical_url_right", "rationale", "risk_tags", "dataset_source"})
    | _REVIEWER_PROVENANCE_KEYS
)
_REVIEWER_REQUIRED_KEYS = frozenset({
    "pair_id", "reviewer_id", "review_round", "label", "label_confidence", "reviewed_at",
    "language", "source_type_left", "source_type_right",
    "title_left", "title_right", "observed_at_left", "observed_at_right",
})

# ── sampling buckets(대표성 추적) — pair 를 결정론으로 한 bucket 에 배정. min target=draft placeholder. ──
SAMPLING_BUCKETS = (
    "likely_same_positive",        # publishable same_event (쉬운 positive)
    "likely_same_hard_negative",   # templated/hard_negative different (FP 유발)
    "ambiguous_multi_candidate",   # ambiguous
    "insufficient_generic",        # generic_title
    "ko_same_event",
    "ko_different_event",
    "mixed_translation",
    "community_only",
    "market_only",
    "catalog_only",
    "far_date_same_title",
    "official_news_same_event",
)
_BUCKET_OTHER = "other"            # 미분류(있으면 경고로 표면화 — 조용한 누락 금지).
# bucket 별 최소 target — **draft placeholder**(통계 근거 미확정; estimate_sample_floor_* 로 재유도 대상).
SAMPLING_MIN_TARGET_DRAFT = 20

# ── sample-floor 통계 추정(normal-approx) — 200/50 magic number 를 근거 있는 값으로 대체하기 위한 추정기. ──
_FLOOR_Z_95 = 1.96   # 95% 신뢰수준


@dataclass(frozen=True)
class ReviewerLabel:
    pair_id: str
    reviewer_id: str
    review_round: int
    label: str
    label_confidence: str
    reviewed_at: str
    language: str
    source_type_left: str
    source_type_right: str
    title_left: str
    title_right: str
    observed_at_left: str
    observed_at_right: str
    reviewer_kind: str = REVIEWER_HUMAN
    canonical_url_left: Optional[str] = None
    canonical_url_right: Optional[str] = None
    rationale: Optional[str] = None
    risk_tags: tuple[str, ...] = ()
    dataset_source: str = SOURCE_LIVE


@dataclass(frozen=True)
class ResolvedGold:
    pair_id: str
    label: Optional[str]              # conflict/insufficient 면 None(단일 gold label 없음)
    language: str
    source_type_left: str
    source_type_right: str
    title_left: str
    title_right: str
    observed_at_left: str
    observed_at_right: str
    agreement_status: str
    resolution_method: str
    reviewer_count: int
    agreement_rate: Optional[float]
    review_status: str               # gold(=agreed/adjudicated) | needs_review(=conflict/insufficient)
    label_confidence: str
    adjudicated_by: Optional[str]
    reviewed_at: str
    dataset_source: str
    risk_tags: tuple[str, ...] = ()


def _validate_reviewer_row(row: dict, *, seen: set[tuple]) -> None:
    keys = set(row)
    extra = keys - REVIEWER_ALLOWED_KEYS
    if extra:
        raise ValueError(f"reviewer label has disallowed keys (raw body/PII/aux 차단): {sorted(extra)}")
    missing = _REVIEWER_REQUIRED_KEYS - keys
    if missing:
        raise ValueError(f"reviewer label missing required keys: {sorted(missing)}")
    rk = row.get("reviewer_kind", REVIEWER_HUMAN)
    if rk in _MODEL_REVIEWER_KINDS:
        # model/self/adjudicator label 은 gold 가 될 수 없다(self-label 금지·옵션 C 거부).
        raise ValueError(f"reviewer_kind {rk!r} cannot be gold (model/self label 금지 — human only)")
    if rk != REVIEWER_HUMAN:
        raise ValueError(f"invalid reviewer_kind {rk!r} (allowed: {sorted(REVIEWER_KINDS)})")
    if not isinstance(row["reviewer_id"], str) or not row["reviewer_id"].strip():
        raise ValueError("reviewer_id required (non-empty str)")
    rnd = row["review_round"]
    if not isinstance(rnd, int) or isinstance(rnd, bool) or rnd < 1:
        raise ValueError(f"review_round must be int ≥ 1, got {rnd!r}")
    key = (row["pair_id"], row["reviewer_id"], rnd)
    if key in seen:
        raise ValueError(f"duplicate reviewer label for (pair_id, reviewer_id, round): {key}")
    seen.add(key)
    if row["label"] not in GOLD_LABELS:
        raise ValueError(f"invalid label {row['label']!r}")
    if row["label_confidence"] not in LABEL_CONFIDENCES:
        raise ValueError(f"invalid label_confidence {row['label_confidence']!r}")
    if row["language"] not in LANGUAGES:
        raise ValueError(f"invalid language {row['language']!r}")
    for side in ("source_type_left", "source_type_right"):
        if row[side] not in SOURCE_TYPES:
            raise ValueError(f"invalid {side} {row[side]!r}")
    for side in ("title_left", "title_right"):
        if not isinstance(row[side], str) or len(row[side]) > _MAX_TITLE_LEN:
            raise ValueError(f"{side} must be str ≤ {_MAX_TITLE_LEN} chars (전문 위장 차단)")
    _validate_reviewed_at(row["reviewed_at"])
    ds = row.get("dataset_source", SOURCE_LIVE)
    if ds not in DATASET_SOURCES:
        raise ValueError(f"invalid dataset_source {ds!r}")
    rt = row.get("risk_tags", [])
    if not isinstance(rt, list) or any(not isinstance(t, str) for t in rt):
        raise ValueError("risk_tags must be a list of str")


def load_reviewer_labels(path: Any) -> list[ReviewerLabel]:
    """reviewer label JSONL 로드·검증. reviewer provenance 필수·model/self label 거부·중복(pair,reviewer,round) 거부."""
    seen: set[tuple] = set()
    out: list[ReviewerLabel] = []
    text = Path(path).read_text(encoding="utf-8")
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"reviewer label line {ln} invalid JSON: {exc}") from exc
        _validate_reviewer_row(row, seen=seen)
        out.append(ReviewerLabel(
            pair_id=row["pair_id"], reviewer_id=row["reviewer_id"], review_round=row["review_round"],
            label=row["label"], label_confidence=row["label_confidence"], reviewed_at=row["reviewed_at"],
            language=row["language"], source_type_left=row["source_type_left"],
            source_type_right=row["source_type_right"], title_left=row["title_left"],
            title_right=row["title_right"], observed_at_left=row["observed_at_left"],
            observed_at_right=row["observed_at_right"], reviewer_kind=row.get("reviewer_kind", REVIEWER_HUMAN),
            canonical_url_left=row.get("canonical_url_left"), canonical_url_right=row.get("canonical_url_right"),
            rationale=row.get("rationale"), risk_tags=tuple(row.get("risk_tags", [])),
            dataset_source=row.get("dataset_source", SOURCE_LIVE),
        ))
    return out


def _latest_per_reviewer(labels: list[ReviewerLabel]) -> dict[str, ReviewerLabel]:
    """한 pair 의 reviewer 별 최신 round label(같은 reviewer 가 여러 round → 마지막 round)."""
    by_reviewer: dict[str, ReviewerLabel] = {}
    for lab in labels:
        cur = by_reviewer.get(lab.reviewer_id)
        if cur is None or lab.review_round > cur.review_round:
            by_reviewer[lab.reviewer_id] = lab
    return by_reviewer


def compute_reviewer_agreement(labels: list[ReviewerLabel]) -> dict:
    """pair 별 reviewer 합의 요약 + 전체 agreement_rate(단순 percent-agreement; Cohen kappa 는 규모 확보 후 future).

    per-pair agreement_rate = 최빈 label 수 / reviewer 수. 전체 agreement_rate = 합의(agreed) 다중-reviewer
    pair 수 / 다중-reviewer pair 수(단일 reviewer pair 는 분모 제외 — 합의 측정 불가)."""
    by_pair: dict[str, list[ReviewerLabel]] = {}
    for lab in labels:
        by_pair.setdefault(lab.pair_id, []).append(lab)
    per_pair: dict[str, dict] = {}
    multi_total = multi_agreed = 0
    for pid, labs in sorted(by_pair.items()):
        reviewers = _latest_per_reviewer(labs)
        votes = [r.label for r in reviewers.values()]
        n = len(votes)
        top = max((votes.count(v) for v in set(votes)), default=0)
        rate = round(top / n, 4) if n else None
        agreed = n >= 2 and top == n
        if n >= 2:
            multi_total += 1
            multi_agreed += 1 if agreed else 0
        per_pair[pid] = {"reviewer_count": n, "agreement_rate": rate, "agreed": agreed,
                         "labels": sorted(votes)}
    return {
        "per_pair": per_pair,
        "multi_reviewer_pairs": multi_total,
        "agreed_pairs": multi_agreed,
        # 다중-reviewer pair 중 전원 합의 비율(단일 reviewer 는 합의 측정 불가라 분모 제외).
        "agreement_rate": round(multi_agreed / multi_total, 4) if multi_total else None,
    }


def _validate_adjudication(pid: str, entry: Any) -> None:
    """adjudication 입력 검증 — **LLM-as-judge 차단**(adjudicator_kind human 만; self-label 금지 대칭).

    adjudication 경로가 reviewer 경로와 달리 무검증이면 model adjudicator label 이 gold 로 새는 뒷문이 된다
    (adversarial Q3). label∈GOLD_LABELS·adjudicated_by 비어있지 않은 human·adjudicator_kind=human 강제(fail-loud)."""
    if not isinstance(entry, dict):
        raise ValueError(f"adjudication[{pid}] must be a dict")
    if entry.get("label") not in GOLD_LABELS:
        raise ValueError(f"adjudication[{pid}] invalid label {entry.get('label')!r}")
    kind = entry.get("adjudicator_kind", REVIEWER_HUMAN)
    if kind != REVIEWER_HUMAN:
        raise ValueError(
            f"adjudication[{pid}] adjudicator_kind {kind!r} cannot be gold (human only — LLM-as-judge 금지)")
    by = entry.get("adjudicated_by")
    if not isinstance(by, str) or not by.strip():
        raise ValueError(f"adjudication[{pid}] adjudicated_by required (non-empty human reviewer id)")


def resolve_gold_from_reviewers(
    labels: list[ReviewerLabel], *, adjudications: Optional[dict[str, dict]] = None
) -> list[ResolvedGold]:
    """reviewer label → resolved gold. **conflict 는 자동 gold 금지·단일 reviewer 는 provisional**.

    adjudications: pair_id → {"label": <GOLD_LABELS>, "adjudicated_by": <human id>, "adjudicator_kind": "human"}
    (conflict 를 사람 lead 가 판정 — model adjudicator 거부). 규칙: 1명=insufficient_reviews(needs_review) ·
    2+전원합의=agreed(gold) · 2+불일치+adjudication=adjudicated(gold) · 2+불일치+미adjudication=conflict(needs_review)."""
    adj = adjudications or {}
    for _pid, _entry in adj.items():
        _validate_adjudication(_pid, _entry)   # 무검증 신뢰 입력 차단(LLM adjudicator → gold 뒷문 봉인)
    by_pair: dict[str, list[ReviewerLabel]] = {}
    for lab in labels:
        by_pair.setdefault(lab.pair_id, []).append(lab)
    out: list[ResolvedGold] = []
    for pid, labs in sorted(by_pair.items()):
        reviewers = _latest_per_reviewer(labs)
        rl = list(reviewers.values())
        n = len(rl)
        votes = [r.label for r in rl]
        top = max((votes.count(v) for v in set(votes)), default=0)
        rate = round(top / n, 4) if n else None
        rep = rl[0]   # 대표 row(title/source/lang content — 모든 reviewer 가 같은 worksheet 행을 봄)
        reviewed_at = max(r.reviewed_at for r in rl)
        confidences = [r.label_confidence for r in rl]
        # 결정 label·status.
        label: Optional[str]
        if n == 1:
            status, method, review_status, label, adjby = (
                AGREE_INSUFFICIENT, RESOLUTION_SINGLE, REVIEW_NEEDS, votes[0], None)
            conf = rl[0].label_confidence  # 단일 reviewer → 그 confidence(보통 저신뢰 취급)
        elif top == n:
            status, method, review_status, label, adjby = (
                AGREE_AGREED, RESOLUTION_AGREEMENT, REVIEW_GOLD, votes[0], None)
            conf = _min_confidence(confidences)
        elif pid in adj and adj[pid].get("label") in GOLD_LABELS:
            status, method, review_status, label, adjby = (
                AGREE_ADJUDICATED, RESOLUTION_ADJUDICATED, REVIEW_GOLD,
                adj[pid]["label"], adj[pid].get("adjudicated_by"))
            conf = "medium"   # adjudication 으로 해소된 conflict → 중간 신뢰(만장일치 아님)
        else:
            status, method, review_status, label, adjby = (
                AGREE_CONFLICT, RESOLUTION_NONE, REVIEW_NEEDS, None, None)
            conf = "low"
        out.append(ResolvedGold(
            pair_id=pid, label=label, language=rep.language,
            source_type_left=rep.source_type_left, source_type_right=rep.source_type_right,
            title_left=rep.title_left, title_right=rep.title_right,
            observed_at_left=rep.observed_at_left, observed_at_right=rep.observed_at_right,
            agreement_status=status, resolution_method=method, reviewer_count=n,
            agreement_rate=rate, review_status=review_status, label_confidence=conf,
            adjudicated_by=adjby, reviewed_at=reviewed_at, dataset_source=rep.dataset_source,
            risk_tags=rep.risk_tags,
        ))
    return out


_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def _min_confidence(confs: list[str]) -> str:
    """reviewer confidence 들의 최소(보수 — 한 명이라도 low 면 low)."""
    return min(confs, key=lambda c: _CONF_ORDER.get(c, 0)) if confs else "low"


def resolved_to_gold_pairs(resolved: list[ResolvedGold]) -> list[GoldPair]:
    """resolved gold 중 **review_status='gold'(agreed/adjudicated)만** GoldPair 로 — metric 산입 대상.

    conflict/insufficient 는 제외(자동 gold 금지). reviewed_by 는 resolution_method 로 기록(provenance)."""
    out: list[GoldPair] = []
    for r in resolved:
        if r.review_status != REVIEW_GOLD or r.label is None:
            continue
        out.append(GoldPair(
            pair_id=r.pair_id, label=r.label, language=r.language,
            source_type_left=r.source_type_left, source_type_right=r.source_type_right,
            title_left=r.title_left, title_right=r.title_right,
            observed_at_left=r.observed_at_left, observed_at_right=r.observed_at_right,
            reviewed_by=f"{r.resolution_method}:{r.reviewer_count}", reviewed_at=r.reviewed_at,
            review_status=REVIEW_GOLD, label_confidence=r.label_confidence,
            dataset_source=r.dataset_source, rationale=None, risk_tags=r.risk_tags,
        ))
    return out


def assign_sampling_bucket(
    *, language: str, source_type_left: str, source_type_right: str, label: str, risk_tags: tuple[str, ...]
) -> str:
    """pair → sampling bucket(결정론·우선순위). 미분류는 _BUCKET_OTHER(경고로 표면화)."""
    tags = set(risk_tags)
    pair_types = {source_type_left, source_type_right}
    if "hard_negative" in tags:
        return "likely_same_hard_negative"
    if "far_date" in tags:
        return "far_date_same_title"
    if "translation" in tags:
        return "mixed_translation"
    if pair_types == {"community"}:
        return "community_only"
    if "market" in pair_types and "official" not in pair_types and "article" not in pair_types:
        return "market_only"
    if pair_types == {"catalog"}:
        return "catalog_only"
    if label == LABEL_AMBIGUOUS:
        return "ambiguous_multi_candidate"
    if "generic_title" in tags:
        return "insufficient_generic"
    if language == "ko" and label == LABEL_SAME:
        return "ko_same_event"
    if language == "ko" and label == LABEL_DIFFERENT:
        return "ko_different_event"
    if label == LABEL_SAME and "official" in pair_types:
        return "official_news_same_event"
    if label == LABEL_SAME:
        return "likely_same_positive"
    # 태그 없는 insufficient(판단 불가)도 other 가 아니라 insufficient bucket 으로(대표성 커버리지 공백 차단·Q6).
    if label == LABEL_INSUFFICIENT:
        return "insufficient_generic"
    return _BUCKET_OTHER


def summarize_sampling_buckets(items: list) -> dict:
    """ReviewerLabel|ResolvedGold|GoldPair 목록 → bucket 분포 + 부족 bucket 경고(draft min target).

    each item 은 language/source_type_left/right/label/risk_tags 속성 보유(공통). label=None(conflict)은 분류 제외."""
    counts: dict[str, int] = {b: 0 for b in SAMPLING_BUCKETS}
    counts[_BUCKET_OTHER] = 0
    for it in items:
        lbl = getattr(it, "label", None)
        if lbl is None:
            continue
        b = assign_sampling_bucket(
            language=it.language, source_type_left=it.source_type_left,
            source_type_right=it.source_type_right, label=lbl, risk_tags=tuple(getattr(it, "risk_tags", ())),
        )
        counts[b] = counts.get(b, 0) + 1
    under = sorted(b for b in SAMPLING_BUCKETS if counts[b] < SAMPLING_MIN_TARGET_DRAFT)
    return {
        "by_bucket": counts,
        "min_target_draft": SAMPLING_MIN_TARGET_DRAFT,
        "under_filled_buckets": under,          # draft target 미달 bucket(대표성 경고)
        "unclassified": counts[_BUCKET_OTHER],  # >0 이면 bucket 규칙 보강 필요(조용한 누락 금지)
    }


def estimate_sample_floor_for_precision(target_precision: float = 0.98, half_width: float = 0.02,
                                        z: float = _FLOOR_Z_95) -> int:
    """precision 을 ±half_width 신뢰구간으로 추정하는 데 필요한 **양성 예측(TP+FP) 수**(normal-approx).

    n ≈ z²·p(1−p)/e². 예: precision 0.98·±0.02·95% → ~189. 기존 GOLD_MERGE_MIN_LIVE_GOLD=200 은
    이 추정의 거친 근사(positive 기준)이며 통계적으로 재유도되어야 함을 보이기 위한 추정기."""
    p = min(max(target_precision, 0.0), 1.0)
    if half_width <= 0:
        raise ValueError("half_width must be > 0")
    return int(math.ceil((z * z * p * (1.0 - p)) / (half_width * half_width)))


def estimate_sample_floor_for_fpr(target_fpr: float = 0.01, half_width: float = 0.01,
                                  z: float = _FLOOR_Z_95) -> int:
    """FPR 을 ±half_width 로 추정하는 데 필요한 **음성(FP+TN) 수**(normal-approx). 예: FPR 0.01·±0.01·95% → ~381.

    음성 표본 floor 가 양성보다 큼 → hard-negative 를 충분히 oversample 해야 함을 정량화."""
    return estimate_sample_floor_for_precision(target_precision=target_fpr, half_width=half_width, z=z)


def recommended_sample_floors() -> dict:
    """현재 MERGE_GATE 기준(precision 0.98·FPR 0.01)에 대한 통계적 권장 floor — 200/50 placeholder 와 대조."""
    return {
        "recommended_positive_floor": estimate_sample_floor_for_precision(),
        "recommended_negative_floor": estimate_sample_floor_for_fpr(),
        "draft_live_gold_floor": GOLD_MERGE_MIN_LIVE_GOLD,
        "draft_korean_gold_floor": GOLD_MERGE_MIN_KOREAN_GOLD,
        "note": "draft floor(200/50)는 placeholder — recommended_*(normal-approx)로 재유도 필요. "
                "특히 korean 50·negative floor 는 통계적으로 낙관적(R-GoldSamplingBias·R-KoreanSemanticCalibration).",
    }


def generate_labeling_protocol_report(
    labels: list[ReviewerLabel], *, total_exported: Optional[int] = None,
    adjudications: Optional[dict[str, dict]] = None,
) -> dict:
    """reviewer label → 운영 labeling protocol report(agreement·resolution·sampling·gold/merge readiness).

    **자동 병합 0**·gold(agreed/adjudicated)만 metric 산입·conflict/single 은 gold 아님(별도 카운트)."""
    agreement = compute_reviewer_agreement(labels)
    resolved = resolve_gold_from_reviewers(labels, adjudications=adjudications)
    gold_pairs = resolved_to_gold_pairs(resolved)
    status_counts: dict[str, int] = {s: 0 for s in AGREEMENT_STATUSES}
    for r in resolved:
        status_counts[r.agreement_status] = status_counts.get(r.agreement_status, 0) + 1
    gold_report = generate_gold_eval_report(gold_pairs) if gold_pairs else None
    return {
        "total_pairs_exported": total_exported,
        "reviewer_labels_count": len(labels),
        "distinct_pairs": len(resolved),
        "resolved_gold_count": len(gold_pairs),
        "agreed_count": status_counts[AGREE_AGREED],
        "adjudicated_count": status_counts[AGREE_ADJUDICATED],
        "conflict_count": status_counts[AGREE_CONFLICT],
        "insufficient_reviews_count": status_counts[AGREE_INSUFFICIENT],
        "agreement_rate": agreement["agreement_rate"],
        "multi_reviewer_pairs": agreement["multi_reviewer_pairs"],
        "by_agreement_status": status_counts,
        "sampling": summarize_sampling_buckets(resolved),
        "sample_floors": recommended_sample_floors(),
        # gold(agreed/adjudicated)만으로 산출한 metric/merge readiness — gold 0이면 None.
        "gold_metrics": None if gold_report is None else {
            "gold_count": gold_report["gold_count"],
            "gold_precision": gold_report["gold_precision"],
            "gold_fpr": gold_report["gold_fpr"],
            "gold_recall": gold_report["gold_recall"],
            "gold_by_language": gold_report["gold_by_language"],
            "merge_readiness": gold_report["merge_readiness"],
        },
        "auto_merged": 0,
    }


# ════════════════════════════════════════════════════════════════════════════════════
# ADR#46 — live-derived labeling packet + sampling operationalization
# ════════════════════════════════════════════════════════════════════════════════════
# ADR#43 export 는 adjudication → **워크시트 JSONL**(predicted_status/score/reason 포함·label='unlabeled')까지만
# 만들고, ADR#45 `resolve_gold_from_reviewers` 는 **이미 손으로 작성된 ReviewerLabel** 만 받는다. 그 사이의 운영
# 단계 — live-derived 후보를 **bucket 별로 샘플링**하고, **reviewer 에게 배정**하고, **model 판정(predicted_status)을
# 차폐**(bias 0)한 labeling packet 으로 변환하고, **sampling deficit/표본 floor 를 report** 하는 단계 — 가 비어 있었다.
# 이 계층이 그 다리다(옵션 A=JSONL packet generator; B=DB queue future·schema migratable 유지; C=synthetic-only 금지).
#
# **불변(상속):** DB/migration 0·결정론·자동 병합 0·raw body/PII 차단. **추가 불변:** packet 에 model 판정
# (predicted_status/score/reason/label) **구조적 미포함**(bias 차단) — labeler 는 정답/모델 추정을 보지 못한다.
# packet 은 **internal-only ops artifact**(public API 미노출). 실 reviewer/충원/대표성은 여전히 0(R-ReviewerAgreement
# ·R-GoldSamplingBias 부분진전·완전종결 금지) — packet 은 그 운영을 가능케 하는 scaffold 일 뿐 실 gold 가 아니다.

# predicted_status 도메인 — ADR#42 adjudicator(`ADJUDICATION_STATUSES`)와 동기. packet **입력**(워크시트)에만 있고
# packet **출력**에는 미포함(bias 차단). 여기에 두는 건 bucket 라우팅 입력 검증용(import 결합 회피·기존 모듈 패턴).
PRED_LIKELY_SAME = "likely_same_event"
PRED_AMBIGUOUS = "ambiguous"
PRED_LIKELY_DIFFERENT = "likely_different_event"
PRED_INSUFFICIENT = "insufficient_features"
PREDICTED_STATUSES = frozenset({PRED_LIKELY_SAME, PRED_AMBIGUOUS, PRED_LIKELY_DIFFERENT, PRED_INSUFFICIENT})

# ── candidate bucket(라벨 **전** — predicted_status/reason/lang/source_type/risk_tags 기반). ADR#45 SAMPLING_BUCKETS
# (라벨 **후** — 정답 label 기반)와 **별개**. *_predicted=모델 추정 stratum(내부 ops 전용)·*_guard=source role 가드. ──
CANDIDATE_BUCKETS = (
    "likely_same_predicted",        # predicted likely_same(영어/일반 positive)
    "ambiguous_predicted",          # predicted ambiguous(eval 가장 중요 — oversample)
    "hard_negative",                # predicted different / templated(FP 유발 — 음성 floor 충당)
    "ko_same_event_candidate",
    "ko_different_event_candidate",
    "mixed_translation",            # 혼합 언어/번역(한국어 캘리브레이션)
    "paraphrase",
    "template_collision",
    "far_date_same_title",          # 같은 제목·먼 시점(reason=far_date_distance)
    "generic_title",                # 신호 부족(reason=generic_title / predicted insufficient)
    "community_guard",              # community-only — merge anchor 아님(역할 가드)
    "market_guard",                 # market/signal-only — signal 역할 가드
    "catalog_guard",                # catalog-only — entity enrichment 가드
    "unknown_guard",                # 미지/빈 source_type — fail-closed 가드
    "official_news_positive",       # predicted likely_same + official/article core
)
_CANDIDATE_BUCKET_OTHER = "other_candidate"   # 미분류(>0 이면 경고로 표면화 — 조용한 누락 금지)

# bucket 별 sampling target(draft) — **oversample**: hard_negative/ambiguous/KO/mixed > easy positive. min target
# 통계 근거는 estimate_sample_floor_* 로 재유도 대상(placeholder·R-GoldSamplingBias). guard 는 역할 검증용 소량.
CANDIDATE_BUCKET_TARGETS = {
    "likely_same_predicted": 20,
    "ambiguous_predicted": 30,
    "hard_negative": 40,            # 음성(FPR) floor 381 충당 위해 최대 oversample
    "ko_same_event_candidate": 30,
    "ko_different_event_candidate": 30,
    "mixed_translation": 25,
    "paraphrase": 25,
    "template_collision": 25,
    "far_date_same_title": 20,
    "generic_title": 15,
    "community_guard": 15,
    "market_guard": 15,
    "catalog_guard": 15,
    "unknown_guard": 15,
    "official_news_positive": 20,
}

# packet assignment 상태.
ASSIGN_ASSIGNED = "assigned"
ASSIGN_IN_REVIEW = "in_review"
ASSIGN_COMPLETED = "completed"
ASSIGNMENT_STATUSES = frozenset({ASSIGN_ASSIGNED, ASSIGN_IN_REVIEW, ASSIGN_COMPLETED})
DEFAULT_REVIEWERS_PER_PAIR = 2     # 동일 pair 를 최소 2명에 배정(single=insufficient·gold 아님)

# packet 허용 키 = pair content + assignment metadata. predicted_status/score/reason/label 은 **미포함**(bias 차단).
_PACKET_ASSIGNMENT_KEYS = frozenset({
    "packet_id", "candidate_link_id", "reviewer_id", "review_round", "assignment_status",
    "sampling_bucket", "instructions",
})
PACKET_ALLOWED_KEYS = (
    frozenset({"pair_id", "language", "source_type_left", "source_type_right",
               "title_left", "title_right", "observed_at_left", "observed_at_right",
               "canonical_url_left", "canonical_url_right", "risk_tags"})
    | _PACKET_ASSIGNMENT_KEYS
)
_PACKET_REQUIRED_KEYS = frozenset({
    "packet_id", "pair_id", "reviewer_id", "review_round", "assignment_status", "sampling_bucket",
    "language", "source_type_left", "source_type_right",
    "title_left", "title_right", "observed_at_left", "observed_at_right",
})
# packet 에 들어오면 안 되는 model 판정 누출 키(bias) — allowlist 로도 막히지만 명시 fail-loud(진단 메시지).
_PACKET_FORBIDDEN_VERDICT_KEYS = frozenset({"predicted_status", "score", "reason", "label"})

# labeler 에게 보이는 지시(model 판정 withheld 명시).
_PACKET_INSTRUCTIONS = (
    "label same_event/different_event/ambiguous/insufficient using titles/metadata only; "
    "do not use raw body; model prediction withheld (no bias)"
)


@dataclass(frozen=True)
class LabelingPacketItem:
    packet_id: str
    pair_id: str
    reviewer_id: str
    review_round: int
    assignment_status: str
    sampling_bucket: str
    language: str
    source_type_left: str
    source_type_right: str
    title_left: str
    title_right: str
    observed_at_left: str
    observed_at_right: str
    candidate_link_id: Optional[str] = None
    canonical_url_left: Optional[str] = None
    canonical_url_right: Optional[str] = None
    risk_tags: tuple[str, ...] = ()
    instructions: str = _PACKET_INSTRUCTIONS


def assign_candidate_bucket(
    *, predicted_status: str, reason: str, language: str,
    source_type_left: str, source_type_right: str, risk_tags: tuple[str, ...]
) -> str:
    """라벨 **전** 후보 → candidate bucket(결정론·우선순위). source role 가드/fail-closed 우선, 그다음 risk tag,
    그다음 reason(far_date/generic), 마지막 predicted_status. 미분류는 _CANDIDATE_BUCKET_OTHER(경고)."""
    tags = set(risk_tags)
    pair_types = {source_type_left, source_type_right}
    # 1) fail-closed / source role 가드(merge anchor 아님). 빈/미지 source_type 또는 단일-역할.
    if (reason == "unknown_source_type_fail_closed" or "unknown" in pair_types
            or not source_type_left or not source_type_right):
        return "unknown_guard"
    if pair_types == {"community"}:
        return "community_guard"
    if ({"market", "signal"} & pair_types) and not ({"official", "article"} & pair_types):
        return "market_guard"   # market/signal-only(evidence layer 는 'signal'·eval enum 은 'market')
    if pair_types == {"catalog"}:
        return "catalog_guard"
    # 2) 명시 risk tag(synthetic fixture 가 줄 수 있음; live 워크시트는 보통 empty).
    if "hard_negative" in tags:
        return "hard_negative"
    if "translation" in tags or language == "mixed":
        return "mixed_translation"
    if "paraphrase" in tags:
        return "paraphrase"
    if "template" in tags:
        return "template_collision"
    # 3) reason 파생(adjudicator classify reason).
    if reason == "far_date_distance":
        return "far_date_same_title"
    if reason == "generic_title":
        return "generic_title"
    # 4) predicted_status 기반.
    if predicted_status == PRED_AMBIGUOUS:
        return "ambiguous_predicted"
    if predicted_status == PRED_INSUFFICIENT:
        return "generic_title"
    if predicted_status == PRED_LIKELY_DIFFERENT:
        return "ko_different_event_candidate" if language == "ko" else "hard_negative"
    if predicted_status == PRED_LIKELY_SAME:
        if language == "ko":
            return "ko_same_event_candidate"
        if {"official", "article"} & pair_types:
            return "official_news_positive"
        return "likely_same_predicted"
    return _CANDIDATE_BUCKET_OTHER


def _bucket_of_row(r: dict) -> str:
    return assign_candidate_bucket(
        predicted_status=str(r.get("predicted_status", "")),
        reason=str(r.get("reason", "")),
        language=str(r.get("language", "unknown")),
        source_type_left=str(r.get("source_type_left", "")),
        source_type_right=str(r.get("source_type_right", "")),
        risk_tags=tuple(r.get("risk_tags", [])),
    )


# ── selection method(ADR#47 옵션 D) — bucket cap 내 선택 **순서**. 둘 다 결정론·재현 가능(무작위 아님). ──
# pair_id_order(ADR#46 기본): pair_id 오름차순 — bucket 이 cap 초과 시 **낮은 pair_id 가 항상 당첨**(정렬 편향).
# bucket_hash(ADR#47): sha256(pair_id) 순 — bucket 내 균일 분산 결정론 표집(정렬 편향 제거·재현 가능).
# cap 미만 bucket(현 데이터 규모)에서는 두 방법의 **선택 집합이 동일**(효과는 over-cap 에서만 발생).
SELECTION_PAIR_ID_ORDER = "deterministic_pair_id_order_cap"
SELECTION_BUCKET_HASH = "deterministic_bucket_hash_cap"
SELECTION_METHODS = frozenset({SELECTION_PAIR_ID_ORDER, SELECTION_BUCKET_HASH})


def _selection_sort_key(r: dict, method: str) -> str:
    """선택 정렬 키(결정론). bucket_hash 는 pair_id 의 sha256 hexdigest(정렬 편향 제거·재현 가능)."""
    pid = str(r.get("pair_id", ""))
    if method == SELECTION_BUCKET_HASH:
        return hashlib.sha256(pid.encode("utf-8")).hexdigest()
    return pid


def _sample_candidate_pairs(
    worksheet_rows: list[dict], *, targets: Optional[dict[str, int]] = None,
    selection_method: str = SELECTION_PAIR_ID_ORDER,
) -> list[tuple[str, dict]]:
    """worksheet rows → 선택된 [(bucket, row)](결정론·bucket target 까지 cap·초과분 drop).

    selection_method=pair_id_order(ADR#46 기본·pair_id 정렬) | bucket_hash(ADR#47·sha256(pair_id) 정렬·정렬
    편향 제거). 둘 다 재현 가능(무작위 아님). cut-off 초과분은 summarize 의 over/under 로 가시화."""
    if selection_method not in SELECTION_METHODS:
        raise ValueError(f"unknown selection_method {selection_method!r}")
    tgt = targets or CANDIDATE_BUCKET_TARGETS
    per_bucket: dict[str, int] = {}
    out: list[tuple[str, dict]] = []
    for r in sorted(worksheet_rows, key=lambda x: _selection_sort_key(x, selection_method)):
        bucket = _bucket_of_row(r)
        cap = tgt.get(bucket, SAMPLING_MIN_TARGET_DRAFT)
        if per_bucket.get(bucket, 0) >= cap:
            continue   # over-target — 본 round 미포함(drop 은 summarize 의 over/under 로 가시화)
        per_bucket[bucket] = per_bucket.get(bucket, 0) + 1
        out.append((bucket, r))
    return out


def _packet_item(
    packet_id: str, r: dict, bucket: str, reviewer_id: str, *,
    review_round: int = 1, assignment_status: str = ASSIGN_ASSIGNED,
) -> LabelingPacketItem:
    """worksheet row → LabelingPacketItem(predicted_status/score/reason **제거**·assignment 부여)."""
    return LabelingPacketItem(
        packet_id=packet_id, pair_id=str(r["pair_id"]), reviewer_id=reviewer_id,
        review_round=review_round, assignment_status=assignment_status, sampling_bucket=bucket,
        language=str(r.get("language", "unknown")),
        source_type_left=r["source_type_left"], source_type_right=r["source_type_right"],
        title_left=r["title_left"], title_right=r["title_right"],
        observed_at_left=r["observed_at_left"], observed_at_right=r["observed_at_right"],
        candidate_link_id=str(r["pair_id"]),   # pair_id == link_id(ADR#43 export) — 명시 보존
        canonical_url_left=r.get("canonical_url_left"), canonical_url_right=r.get("canonical_url_right"),
        risk_tags=tuple(r.get("risk_tags", [])),
    )


def assign_reviewer_packet(
    selected: list[tuple[str, dict]], *, packet_id: str, reviewers: list[str],
    reviewers_per_pair: int = DEFAULT_REVIEWERS_PER_PAIR,
) -> list[LabelingPacketItem]:
    """선택 [(bucket, row)] → reviewer 배정 packet items(결정론 round-robin·동일 pair 를 distinct reviewers_per_pair 명에).

    single(reviewers_per_pair=1)도 허용하나 resolve 단계에서 insufficient(gold 아님)로 처리됨. reviewer 는 human
    allowlist(distinct ≥ reviewers_per_pair) — reviewer_kind 는 ReviewerLabel 단계에서 human 강제(self/model 금지)."""
    if reviewers_per_pair < 1:
        raise ValueError("reviewers_per_pair must be >= 1")
    distinct = list(dict.fromkeys(reviewers))   # 순서 보존 dedup
    if len(distinct) < reviewers_per_pair:
        raise ValueError(
            f"need >= {reviewers_per_pair} distinct reviewers for assignment, got {len(distinct)}")
    items: list[LabelingPacketItem] = []
    for idx, (bucket, r) in enumerate(selected):
        for k in range(reviewers_per_pair):
            rid = distinct[(idx + k) % len(distinct)]
            items.append(_packet_item(packet_id, r, bucket, rid))
    return items


def build_labeling_packet(
    worksheet_rows: list[dict], *, packet_id: str, reviewers: list[str],
    reviewers_per_pair: int = DEFAULT_REVIEWERS_PER_PAIR,
    targets: Optional[dict[str, int]] = None,
    selection_method: str = SELECTION_PAIR_ID_ORDER,
) -> list[LabelingPacketItem]:
    """live-derived 워크시트(adjudication export) → reviewer labeling packet items.

    bucket 샘플링(target cap·oversample·selection_method) → reviewer ≥N 배정 → predicted_status/score/reason
    **차폐**(bias 0). 결정론(재현 가능). internal-only artifact(public 미노출). 자동 병합 0(read-only 변환)."""
    selected = _sample_candidate_pairs(
        worksheet_rows, targets=targets, selection_method=selection_method)
    return assign_reviewer_packet(
        selected, packet_id=packet_id, reviewers=reviewers, reviewers_per_pair=reviewers_per_pair)


def packet_item_to_dict(item: LabelingPacketItem) -> dict:
    """LabelingPacketItem → dict(None/빈 optional 생략·결정론). model 판정 키 부재(구조적 bias 차단)."""
    d = {
        "packet_id": item.packet_id, "pair_id": item.pair_id, "reviewer_id": item.reviewer_id,
        "review_round": item.review_round, "assignment_status": item.assignment_status,
        "sampling_bucket": item.sampling_bucket, "language": item.language,
        "source_type_left": item.source_type_left, "source_type_right": item.source_type_right,
        "title_left": item.title_left, "title_right": item.title_right,
        "observed_at_left": item.observed_at_left, "observed_at_right": item.observed_at_right,
        "instructions": item.instructions,
    }
    if item.candidate_link_id is not None:
        d["candidate_link_id"] = item.candidate_link_id
    if item.canonical_url_left is not None:
        d["canonical_url_left"] = item.canonical_url_left
    if item.canonical_url_right is not None:
        d["canonical_url_right"] = item.canonical_url_right
    if item.risk_tags:
        d["risk_tags"] = list(item.risk_tags)
    return d


def labeler_facing_view(item: LabelingPacketItem) -> dict:
    """reviewer 에게 실제 제시하는 view — **sampling_bucket·model 판정·assignment 내부값 전부 제외**(bias 0).

    pair content(title/source_type/observed/url/language) + 지시 + reviewer_id/round 만. sampling_bucket(예측
    파생 stratum)은 labeler 가 정답을 추론하지 못하도록 제거 — predicted_status 미포함과 동일 원칙."""
    return {
        "pair_id": item.pair_id, "reviewer_id": item.reviewer_id, "review_round": item.review_round,
        "language": item.language,
        "source_type_left": item.source_type_left, "source_type_right": item.source_type_right,
        "title_left": item.title_left, "title_right": item.title_right,
        "observed_at_left": item.observed_at_left, "observed_at_right": item.observed_at_right,
        "canonical_url_left": item.canonical_url_left, "canonical_url_right": item.canonical_url_right,
        "instructions": item.instructions,
    }


def validate_labeling_packet(rows: list[dict]) -> None:
    """packet 행 검증(fail-loud) — model 판정 누출(predicted_status/score/reason/label) 차단·allowlist(raw body/PII)
    ·enum(assignment_status/bucket/language/source_type)·title 길이·(packet_id,pair_id,reviewer_id,round) 중복 거부."""
    seen: set[tuple] = set()
    for r in rows:
        keys = set(r)
        verdict = keys & _PACKET_FORBIDDEN_VERDICT_KEYS
        if verdict:
            raise ValueError(f"packet row leaks model verdict (bias 차단): {sorted(verdict)}")
        extra = keys - PACKET_ALLOWED_KEYS
        if extra:
            raise ValueError(f"packet row has disallowed keys (raw body/PII 차단): {sorted(extra)}")
        missing = _PACKET_REQUIRED_KEYS - keys
        if missing:
            raise ValueError(f"packet row missing required keys: {sorted(missing)}")
        if r["assignment_status"] not in ASSIGNMENT_STATUSES:
            raise ValueError(f"invalid assignment_status {r['assignment_status']!r}")
        if r["sampling_bucket"] not in CANDIDATE_BUCKETS and r["sampling_bucket"] != _CANDIDATE_BUCKET_OTHER:
            raise ValueError(f"invalid sampling_bucket {r['sampling_bucket']!r}")
        if r["language"] not in LANGUAGES:
            raise ValueError(f"invalid language {r['language']!r}")
        for side in ("source_type_left", "source_type_right"):
            if r[side] not in SOURCE_TYPES:
                raise ValueError(f"invalid {side} {r[side]!r}")
        for side in ("title_left", "title_right"):
            if not isinstance(r[side], str) or len(r[side]) > _MAX_TITLE_LEN:
                raise ValueError(f"{side} must be str ≤ {_MAX_TITLE_LEN} chars (전문 위장 차단)")
        if not isinstance(r["reviewer_id"], str) or not r["reviewer_id"].strip():
            raise ValueError("reviewer_id required (non-empty str)")
        rnd = r["review_round"]
        if not isinstance(rnd, int) or isinstance(rnd, bool) or rnd < 1:
            raise ValueError(f"review_round must be int ≥ 1, got {rnd!r}")
        rt = r.get("risk_tags", [])
        if not isinstance(rt, list) or any(not isinstance(t, str) for t in rt):
            raise ValueError("risk_tags must be a list of str")
        key = (r["packet_id"], r["pair_id"], r["reviewer_id"], rnd)
        if key in seen:
            raise ValueError(f"duplicate packet assignment (packet_id,pair_id,reviewer_id,round): {key}")
        seen.add(key)


def write_labeling_packet_jsonl(items: list[LabelingPacketItem], path: Any) -> int:
    """packet items → JSONL(**internal ops artifact**·결정론·sort_keys). 기록 전 validate(verdict/allowlist/enum).

    ⚠ 이 JSONL 은 sampling_bucket 을 포함한다(ops 추적용). **labeler 에게 직접 주지 마라** — labeler-facing 은
    `labeler_facing_view`(bucket·model 판정 제거)다. bucket 미노출은 코드 불변이 아니라 **운영 약속**이다."""
    rows = [packet_item_to_dict(it) for it in items]
    validate_labeling_packet(rows)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(rows)


# floor_check 의 positive/negative/KO bucket 그룹(표본 floor 대조용).
_FLOOR_POSITIVE_BUCKETS = ("likely_same_predicted", "ko_same_event_candidate", "official_news_positive")
_FLOOR_NEGATIVE_BUCKETS = ("hard_negative", "ko_different_event_candidate", "far_date_same_title")
_FLOOR_KO_BUCKETS = ("ko_same_event_candidate", "ko_different_event_candidate")


def summarize_packet_sampling(
    worksheet_rows: list[dict], *, targets: Optional[dict[str, int]] = None,
    packet_items: Optional[list[LabelingPacketItem]] = None,
    selection_method: str = SELECTION_PAIR_ID_ORDER,
) -> dict:
    """worksheet 후보 → sampling 대표성 report(bucket 충원/부족·언어/source_type/risk_tag 분포·표본 floor 대조).

    selected = build 와 **동일** _sample_candidate_pairs(같은 selection_method·결정론 일치). deficit/underfilled 를
    숨기지 않는다(평균 뒤에 한국어/hard-negative 숨기기 금지). synthetic 은 live count 를 부풀리지 않는다(live_vs_synthetic)."""
    tgt = targets or CANDIDATE_BUCKET_TARGETS
    total_by_bucket: dict[str, int] = {b: 0 for b in CANDIDATE_BUCKETS}
    total_by_bucket[_CANDIDATE_BUCKET_OTHER] = 0
    by_language: dict[str, int] = {}
    by_source_type: dict[str, int] = {}
    by_risk_tag: dict[str, int] = {}
    live_vs_synthetic = {SOURCE_LIVE: 0, SOURCE_SYNTHETIC: 0}
    for r in worksheet_rows:
        total_by_bucket[_bucket_of_row(r)] = total_by_bucket.get(_bucket_of_row(r), 0) + 1
        lang = str(r.get("language", "unknown"))
        by_language[lang] = by_language.get(lang, 0) + 1
        st = "|".join(sorted((str(r.get("source_type_left", "")), str(r.get("source_type_right", "")))))
        by_source_type[st] = by_source_type.get(st, 0) + 1
        for t in r.get("risk_tags", []):
            by_risk_tag[t] = by_risk_tag.get(t, 0) + 1
        ds = r.get("dataset_source", SOURCE_LIVE)
        live_vs_synthetic[ds] = live_vs_synthetic.get(ds, 0) + 1

    selected = _sample_candidate_pairs(
        worksheet_rows, targets=targets, selection_method=selection_method)
    selected_by_bucket: dict[str, int] = {b: 0 for b in CANDIDATE_BUCKETS}
    selected_live = 0
    for bucket, r in selected:
        selected_by_bucket[bucket] = selected_by_bucket.get(bucket, 0) + 1
        if r.get("dataset_source", SOURCE_LIVE) == SOURCE_LIVE:
            selected_live += 1
    target_by_bucket = {b: tgt.get(b, SAMPLING_MIN_TARGET_DRAFT) for b in CANDIDATE_BUCKETS}
    deficit_by_bucket = {b: max(0, target_by_bucket[b] - selected_by_bucket[b]) for b in CANDIDATE_BUCKETS}
    oversampled = sorted(b for b in CANDIDATE_BUCKETS if total_by_bucket.get(b, 0) > target_by_bucket[b])
    underfilled = sorted(b for b in CANDIDATE_BUCKETS if selected_by_bucket[b] < target_by_bucket[b])
    selected_count = sum(selected_by_bucket.values())

    floors = recommended_sample_floors()
    pos_sel = sum(selected_by_bucket[b] for b in _FLOOR_POSITIVE_BUCKETS)
    neg_sel = sum(selected_by_bucket[b] for b in _FLOOR_NEGATIVE_BUCKETS)
    ko_sel = sum(selected_by_bucket[b] for b in _FLOOR_KO_BUCKETS)
    return {
        "total_candidates": len(worksheet_rows),
        "selected_count": selected_count,
        # selection 은 **무작위 표집 아님** — bucket cap 까지 결정론 cut-off(pair_id 정렬 또는 sha256 hash 정렬).
        # 대표성은 미입증(R-GoldSamplingBias). "sampling" 이 random 을 함의하지 않도록 method 를 명시.
        "selection_method": selection_method,
        "target_by_bucket": target_by_bucket,
        "selected_by_bucket": selected_by_bucket,
        "total_by_bucket": total_by_bucket,
        "deficit_by_bucket": deficit_by_bucket,
        "oversampled_buckets": oversampled,
        "underfilled_buckets": underfilled,
        "unclassified": total_by_bucket.get(_CANDIDATE_BUCKET_OTHER, 0),   # >0 이면 bucket 규칙 보강(조용한 누락 금지)
        "by_language": by_language,
        "by_source_type": by_source_type,
        "by_risk_tag": by_risk_tag,
        "live_vs_synthetic": live_vs_synthetic,
        "reviewer_assignment_count": len(packet_items) if packet_items is not None else 0,
        # 표본 floor(189/381/draft KO/live) 대조 — selected count 가 floor 에 얼마나 못 미치는지 deficit 로 정직 노출.
        "floor_check": {
            "positive_selected": pos_sel, "positive_floor": floors["recommended_positive_floor"],
            "positive_deficit": max(0, floors["recommended_positive_floor"] - pos_sel),
            "negative_selected": neg_sel, "negative_floor": floors["recommended_negative_floor"],
            "negative_deficit": max(0, floors["recommended_negative_floor"] - neg_sel),
            "ko_selected": ko_sel, "ko_floor": floors["draft_korean_gold_floor"],
            "ko_deficit": max(0, floors["draft_korean_gold_floor"] - ko_sel),
            "live_selected": selected_live, "live_floor": floors["draft_live_gold_floor"],
            "live_deficit": max(0, floors["draft_live_gold_floor"] - selected_live),
        },
        "auto_merged": 0,
    }


def adjudication_queue_from_resolved(resolved: list[ResolvedGold]) -> list[dict]:
    """resolved gold 중 **conflict** pair → adjudication queue(사람 lead 배정 후보). **자동 다수결 gold 금지**.

    conflict 만(insufficient/agreed/adjudicated 제외). raw body/PII 미포함(pair_id·content·합의 메타만). 이 queue 의
    label 은 비어있고 — `_validate_adjudication`(human adjudicator only)을 통과한 사람 판정으로만 gold 가 된다."""
    out: list[dict] = []
    for r in resolved:
        if r.agreement_status != AGREE_CONFLICT:
            continue
        out.append({
            "pair_id": r.pair_id, "language": r.language,
            "source_type_left": r.source_type_left, "source_type_right": r.source_type_right,
            "title_left": r.title_left, "title_right": r.title_right,
            "reviewer_count": r.reviewer_count, "agreement_rate": r.agreement_rate,
            "needs_human_adjudication": True, "adjudicator_kind": REVIEWER_HUMAN,
        })
    return out


def generate_packet_ops_report(
    worksheet_rows: list[dict], *, packet_id: str, reviewers: list[str],
    reviewers_per_pair: int = DEFAULT_REVIEWERS_PER_PAIR,
    targets: Optional[dict[str, int]] = None,
) -> dict:
    """live-derived 워크시트 → packet ops report(packet 생성·sampling 대표성·표본 floor·reviewer 배정). 자동 병합 0.

    **gold 산출 아님** — packet 은 reviewer 배정 scaffold 일 뿐, gold 는 reviewer 가 라벨한 뒤 ADR#45 resolve 로만 생긴다."""
    items = build_labeling_packet(
        worksheet_rows, packet_id=packet_id, reviewers=reviewers,
        reviewers_per_pair=reviewers_per_pair, targets=targets)
    sampling = summarize_packet_sampling(worksheet_rows, targets=targets, packet_items=items)
    return {
        "packet_id": packet_id,
        "candidates_in": len(worksheet_rows),
        "selected_pairs": sampling["selected_count"],
        "packet_items": len(items),               # = selected_pairs × reviewers_per_pair
        "reviewers_per_pair": reviewers_per_pair,
        "distinct_reviewers": len(dict.fromkeys(reviewers)),
        "sampling": sampling,
        "gold_resolved": 0,                        # packet 단계는 gold 0(라벨 전) — 명시
        "auto_merged": 0,
    }
