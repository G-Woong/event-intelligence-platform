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

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.app.services.identity_eval_dataset import (
    ALLOWED_KEYS,
    GOLD_LABELS,
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
