"""Identity evaluation dataset + metrics harness (ADR#43, R-IdentityEvalDataset).

`semantic_identity_adjudicator`(ADR#42)의 status 는 deterministic heuristic **출력**이라 self-labeled —
자기 자신의 precision/recall 을 측정할 수 없다. 실제 Event 병합을 허용하기 전 반드시 **독립 gold label**
대비 precision/FPR/coverage 를 측정해야 한다(false merge = cardinal sin → precision·FPR gate 선결).

이 모듈은:
  - labeled **observation pair**(두 관측의 제목·시점·source_type·url + gold label)를 JSONL 로 로드·검증.
    Event id 비의존(fixture self-contained; 같은 harness 로 live-derived pair 도 평가).
  - 현재 deterministic adjudicator 를 각 pair 에 적용해 예측 status 산출.
  - precision/false-positive-rate/recall/ambiguous·insufficient rate/coverage + 언어/소스타입/risk-tag breakdown.
  - **자동 병합은 하지 않는다**(평가 전용). merge gate 는 문서화만(MERGE_GATE) — 충족돼도 이 모듈이 병합 안 함.

**raw body/PII 금지**: JSONL 키는 ALLOWED_KEYS allowlist 만(body/content/author/email 등 구조적 차단).
제목은 짧은 헤드라인 라벨만. stdlib + adjudicator pure 함수 재사용. 결정론(LLM/network 0).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.services.semantic_identity_adjudicator import (
    ADJ_AMBIGUOUS,
    ADJ_INSUFFICIENT,
    ADJ_LIKELY_DIFFERENT,
    ADJ_LIKELY_SAME,
    EventView,
    build_adjudication_features,
    classify_identity_candidate,
)

# gold label(독립 정답) — adjudicator status 와 구분(이건 사람이/정책이 정한 정답).
LABEL_SAME = "same_event"
LABEL_DIFFERENT = "different_event"
LABEL_AMBIGUOUS = "ambiguous"
LABEL_INSUFFICIENT = "insufficient"
GOLD_LABELS = frozenset({LABEL_SAME, LABEL_DIFFERENT, LABEL_AMBIGUOUS, LABEL_INSUFFICIENT})

LANGUAGES = frozenset({"ko", "en", "mixed", "unknown"})
SOURCE_TYPES = frozenset({"article", "official", "community", "market", "catalog", "search", "unknown"})

# JSONL 행 허용 키(allowlist) — body/raw_text/content/author/email 등은 구조적으로 금지(raw≠eval, PII 차단).
ALLOWED_KEYS = frozenset({
    "pair_id", "label", "language", "source_type_left", "source_type_right",
    "title_left", "title_right", "observed_at_left", "observed_at_right",
    "canonical_url_left", "canonical_url_right", "rationale", "risk_tags",
})
_REQUIRED_KEYS = frozenset({
    "pair_id", "label", "language", "source_type_left", "source_type_right",
    "title_left", "title_right", "observed_at_left", "observed_at_right",
})
_MAX_TITLE_LEN = 512   # 헤드라인 라벨 상한(전문 위장 차단).

# ── merge gate 초안(ADR#43 §4) — 실제 병합 허용 전 충족해야 할 기준. **이번 턴 미적용**(문서/측정만). ──
# 이 기준을 충족해도 production 자동 병합은 켜지 않는다(adversarial 승인·live-derived labeled·embedding 층 선결).
MERGE_GATE = {
    "likely_same_precision_min": 0.98,
    "likely_same_false_positive_rate_max": 0.01,
    "hard_negative_false_positive_max": 0,
    "korean_subset_precision_min": 0.98,
    "note": "문서/측정 전용 — 충족돼도 자동 병합 금지(R-SemanticIdentityAdjudicator·adversarial 승인 선결).",
}


@dataclass(frozen=True)
class EvalPair:
    pair_id: str
    label: str
    language: str
    source_type_left: str
    source_type_right: str
    title_left: str
    title_right: str
    observed_at_left: str
    observed_at_right: str
    canonical_url_left: Optional[str] = None
    canonical_url_right: Optional[str] = None
    rationale: Optional[str] = None
    risk_tags: tuple[str, ...] = ()


def _validate_row(row: dict, *, seen_ids: set[str]) -> None:
    keys = set(row)
    extra = keys - ALLOWED_KEYS
    if extra:
        raise ValueError(f"eval pair has disallowed keys (raw body/PII 차단): {sorted(extra)}")
    missing = _REQUIRED_KEYS - keys
    if missing:
        raise ValueError(f"eval pair missing required keys: {sorted(missing)}")
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
    rt = row.get("risk_tags", [])
    if not isinstance(rt, list) or any(not isinstance(t, str) for t in rt):
        raise ValueError("risk_tags must be a list of str")


def load_eval_pairs(path: Any) -> list[EvalPair]:
    """JSONL labeled pair set 로드·검증. allowlist 키만·중복 pair_id 금지·enum 검증·전문 위장 차단."""
    seen: set[str] = set()
    pairs: list[EvalPair] = []
    text = Path(path).read_text(encoding="utf-8")
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"eval pair line {ln} invalid JSON: {exc}") from exc
        _validate_row(row, seen_ids=seen)
        pairs.append(EvalPair(
            pair_id=row["pair_id"], label=row["label"], language=row["language"],
            source_type_left=row["source_type_left"], source_type_right=row["source_type_right"],
            title_left=row["title_left"], title_right=row["title_right"],
            observed_at_left=row["observed_at_left"], observed_at_right=row["observed_at_right"],
            canonical_url_left=row.get("canonical_url_left"),
            canonical_url_right=row.get("canonical_url_right"),
            rationale=row.get("rationale"),
            risk_tags=tuple(row.get("risk_tags", [])),
        ))
    return pairs


def _parse_dt(raw: str) -> datetime:
    s = (raw or "").strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def pair_to_views(pair: EvalPair) -> tuple[EventView, EventView]:
    """EvalPair → 두 EventView(adjudicator 입력). source_type 단일→tuple."""
    left = EventView("L", pair.title_left, _parse_dt(pair.observed_at_left), (pair.source_type_left,))
    right = EventView("R", pair.title_right, _parse_dt(pair.observed_at_right), (pair.source_type_right,))
    return left, right


def predict_status(pair: EvalPair) -> str:
    """현재 deterministic adjudicator 를 pair 에 적용한 예측 status(pair 단위 → multiple_candidates=False)."""
    left, right = pair_to_views(pair)
    features = build_adjudication_features(left, right, multiple_candidates=False)
    status, _score, _reason = classify_identity_candidate(features)
    return status


def _safe_div(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def _metrics_for(pairs: list[EvalPair], preds: dict[str, str]) -> dict:
    """주어진 pair subset 의 confusion/precision/recall/fpr/rate/coverage."""
    tp = fp = fn = tn = 0
    n_amb = n_insuf = n_same_pred = n_diff_pred = 0
    for p in pairs:
        pred = preds[p.pair_id]
        gold_same = p.label == LABEL_SAME
        pred_same = pred == ADJ_LIKELY_SAME
        if pred_same and gold_same:
            tp += 1
        elif pred_same and not gold_same:
            fp += 1
        elif not pred_same and gold_same:
            fn += 1
        else:
            tn += 1
        if pred == ADJ_AMBIGUOUS:
            n_amb += 1
        elif pred == ADJ_INSUFFICIENT:
            n_insuf += 1
        elif pred == ADJ_LIKELY_SAME:
            n_same_pred += 1
        elif pred == ADJ_LIKELY_DIFFERENT:
            n_diff_pred += 1
    total = len(pairs)
    return {
        "count": total,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "likely_same_precision": _safe_div(tp, tp + fp),
        "likely_same_false_positive_rate": _safe_div(fp, fp + tn),
        "same_event_recall": _safe_div(tp, tp + fn),
        "ambiguous_rate": _safe_div(n_amb, total),
        "insufficient_rate": _safe_div(n_insuf, total),
        # coverage = 단정 예측(likely_same|likely_different) 비율(ambiguous/insufficient = 판단 보류).
        "coverage": _safe_div(n_same_pred + n_diff_pred, total),
    }


def evaluate_adjudicator(pairs: list[EvalPair]) -> dict:
    """labeled pair set 에 현재 adjudicator 를 적용한 평가 metric + 언어/소스타입/risk-tag breakdown.

    **자동 병합 0** — 측정 전용. merge gate(MERGE_GATE)는 보고만 하고 적용하지 않는다(자동 병합 금지)."""
    preds = {p.pair_id: predict_status(p) for p in pairs}
    overall = _metrics_for(pairs, preds)

    by_language: dict[str, dict] = {}
    for lang in sorted({p.language for p in pairs}):
        by_language[lang] = _metrics_for([p for p in pairs if p.language == lang], preds)

    by_source_type: dict[str, dict] = {}
    for key in sorted({"|".join(sorted((p.source_type_left, p.source_type_right))) for p in pairs}):
        subset = [p for p in pairs if "|".join(sorted((p.source_type_left, p.source_type_right))) == key]
        by_source_type[key] = _metrics_for(subset, preds)

    by_risk_tag: dict[str, dict] = {}
    for tag in sorted({t for p in pairs for t in p.risk_tags}):
        by_risk_tag[tag] = _metrics_for([p for p in pairs if tag in p.risk_tags], preds)

    # hard_negative false positive(gate 핵심): risk_tag 'hard_negative' 이고 gold≠same 인데 likely_same 예측.
    hard_neg_fp = sum(
        1 for p in pairs
        if "hard_negative" in p.risk_tags and p.label != LABEL_SAME and preds[p.pair_id] == ADJ_LIKELY_SAME
    )

    ks = by_language.get("ko", {})
    gate = evaluate_merge_gate(overall, korean=ks, hard_negative_fp=hard_neg_fp)
    return {
        "overall": overall,
        "by_language": by_language,
        "by_source_type": by_source_type,
        "by_risk_tag": by_risk_tag,
        "hard_negative_false_positive": hard_neg_fp,
        "merge_gate": gate,
        # 자동 병합 0 의 명시적 증거(report 소비자가 'merge 안 함'을 확인) — 항상 0.
        "auto_merged": 0,
    }


def evaluate_merge_gate(overall: dict, *, korean: dict, hard_negative_fp: int) -> dict:
    """현재 metric 이 merge gate 초안(MERGE_GATE)을 충족하는지 — **보고용**(충족돼도 자동 병합 금지)."""
    prec = overall.get("likely_same_precision")
    fpr = overall.get("likely_same_false_positive_rate")
    kprec = korean.get("likely_same_precision") if korean else None
    checks = {
        "precision_ok": prec is not None and prec >= MERGE_GATE["likely_same_precision_min"],
        "fpr_ok": fpr is not None and fpr <= MERGE_GATE["likely_same_false_positive_rate_max"],
        "hard_negative_fp_ok": hard_negative_fp <= MERGE_GATE["hard_negative_false_positive_max"],
        "korean_precision_ok": kprec is not None and kprec >= MERGE_GATE["korean_subset_precision_min"],
    }
    return {
        **checks,
        "passed": all(checks.values()),
        "auto_merge_enabled": False,   # 불변 — gate 충족 여부와 무관하게 production 자동 병합 OFF.
    }
