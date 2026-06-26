"""ADR#66 — reviewer label operations + gold calibration preflight (병합 0·LLM 0·embedding 0·DB 0).

ADR#65 가 만든 것: cross-source pair → semantic scorer top-k → near-match reviewer queue(score/rationale labeler
숨김). 그 다음 병목: **그 queue 가 실제 사람 라벨 운영으로 이어지지 않는다** — packet export → label import →
agreement/conflict/adjudication → gold 승격 → MERGE_GATE calibration readiness 의 운영 경로가 닫혀있지 않다.

이 모듈은 **재구현이 아니라 얇은 운영 orchestrator** 다. 무거운 일은 전부 기존 단일 출처가 한다:
  - packet/labeler-facing view: `near_match_reviewer_queue.build_near_match_reviewer_queue`(score 0·bias 0)
  - label import/검증: `identity_human_labeling.load_reviewer_labels`(allowlist·forbidden field fail-loud·model label 거부)
  - gold 승격/agreement/conflict: `resolve_gold_from_reviewers`/`resolved_to_gold_pairs`/`compute_reviewer_agreement`/
    `adjudication_queue_from_resolved`(single/unanimous/conflict/adjudicated)
  - calibration: `evaluate_gold_merge_readiness`(live_derived gold only·표본 floor·MERGE_GATE)

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **reviewer_id pseudonymization**: 공개 report 에 raw reviewer_id 출력 금지(PII) — 결정론 해시만.
  - **production vs synthetic/test gold 분리 집계**: label_source(production/synthetic_fixture/test_fixture)로
    production_gold_count(=live_derived & production)와 synthetic_gold_count 를 명시 분리(synthetic 으로 gold 부풀리기 차단).
  - **§7 calibration preflight**: merge_gate_ready·precision/FPR denominator readiness·top_k bias warning·hard negative
    coverage·korean calibration 을 한 report 로 종합.
  - **optional real label file ingestion**: 파일 없음 = 실패가 아니라 no_labels report + next_action(정직).

절대 불변(상속·상용 안전 계약):
  - **no merge / no auto-merge**: gold 는 metric/문서 전용. merge_allowed=False·no_merge_without_gold 불변.
  - **production_gold_count 0 정직**: 실 production reviewer label 이 없으면 0 유지(synthetic 은 simulated only).
  - **single reviewer ≠ gold**·**conflict ≠ 자동 다수결 gold**·**model/self/LLM label ≠ gold**(human only).
  - **labeler 숨김**: score/rationale/predicted_status 는 labeler-facing view 에 0(validate_labeling_packet fail-loud).
  - **secret 0 / raw body 0**: allowlist 가 body/score/api_key 구조적 차단. reviewer_id 는 해시로만 report.
  - **DB 0 / LLM·embedding 실호출 0 / public IU 0**.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Optional

from backend.app.services.identity_eval_dataset import (
    LABEL_DIFFERENT,
    LABEL_SAME,
    MERGE_GATE,
)
from backend.app.services.identity_human_labeling import (
    AGREE_ADJUDICATED,
    AGREE_AGREED,
    AGREE_CONFLICT,
    GOLD_MERGE_MIN_KOREAN_GOLD,
    GOLD_MERGE_MIN_LIVE_GOLD,
    RESOLUTION_SINGLE,
    REVIEWER_HUMAN,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    GoldPair,
    ReviewerLabel,
    adjudication_queue_from_resolved,
    compute_reviewer_agreement,
    evaluate_gold_merge_readiness,
    load_reviewer_labels,
    resolve_gold_from_reviewers,
    resolved_to_gold_pairs,
)
from backend.app.tools.near_match_reviewer_queue import (
    EMBEDDING_LLM_ADJUDICATOR_INTERFACE,
    build_near_match_reviewer_queue,
)

OPERATION_NAME = "reviewer_label_operations"

# ── label_source(operation-level provenance) — frozen ReviewerLabel 의 dataset_source(2-way) 위에 얹는 3-way 태그. ──
# production: 실 운영 reviewer label(live_derived pair 와 결합 시에만 production gold). synthetic_fixture: calibration
# 연습용(simulated gold only). test_fixture: 경로 검증용(절대 gold 아님). production gold 는 **production AND live_derived**.
LABEL_SOURCE_PRODUCTION = "production"
LABEL_SOURCE_SYNTHETIC = "synthetic_fixture"
LABEL_SOURCE_TEST = "test_fixture"
LABEL_SOURCES = frozenset({LABEL_SOURCE_PRODUCTION, LABEL_SOURCE_SYNTHETIC, LABEL_SOURCE_TEST})

# 명시적 forbidden label fields — load_reviewer_labels 의 allowlist 가 이미 구조적으로 거부하지만, block_reason 을
# 구체적으로 분류(어떤 종류가 새려 했는지)하기 위한 참조 집합. score/rationale 모델값·raw body·secret.
FORBIDDEN_LABEL_FIELDS = frozenset({
    "semantic_score", "model_score", "predicted_status", "model_rationale",
    "raw_body", "body", "content", "secret", "api_key", "provider_secret",
})

_REVIEWER_ID_PREFIX = "rv_"   # pseudonym prefix(raw reviewer_id 미노출 — PII 차단).

# §9 Agent / Intelligence Unit contract — Agent 는 reviewer/gold 운영을 **계획**할 수 있으나 merge 는 불가.
REVIEWER_OPS_AGENT_CONTRACT = {
    "can": [
        "reviewer packet export 계획", "reviewer label collection 계획",
        "agreement/adjudication workflow 계획", "gold calibration readiness 계획",
        "hard negative balancing 계획", "korean calibration 계획", "next reviewer action 도출",
    ],
    "cannot": [
        "reviewer label 조작", "score 를 truth 로 사용", "same-event 확정", "merge 실행",
        "public Intelligence Unit 생성", "community reaction 을 event anchor 로 사용",
        "market/catalog 를 event anchor 로 사용", "secret 읽기/출력",
    ],
    "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go for merge(이번 턴 호출 0).
}

# block_reason → next_action.
_NEXT_ACTION = {
    "no_packet": "cross-source 후보가 없음 — targeted same-event acquisition(source pair/topic/time window) 후 재시도",
    "no_labels": "reviewer 에게 packet export → 실 human label(JSONL) 수집 후 label_path 로 재import",
    "label_file_missing": "label_path 가 가리키는 파일이 없음 — 경로 확인 또는 packet 배포 후 라벨 수집",
    "malformed_label_file": "label file JSON/schema 오류 — 행 형식(JSONL·allowlist 키) 점검 후 재import",
    "forbidden_field_in_label": "label 에 score/rationale/raw body/secret 누출 — 해당 필드 제거(reviewer-facing 만 허용)",
    "model_label_rejected": "model/self/LLM label 은 gold 불가(human only) — reviewer_kind=human 인 사람 라벨만 import",
    "no_production_labels": "label_source 가 production 아님(synthetic/test) — production gold 0 유지(경로 검증만)",
    "insufficient_gold_for_calibration": (
        f"production gold < live floor({GOLD_MERGE_MIN_LIVE_GOLD}) — 실 reviewer label 충원 필요"),
    "korean_gold_insufficient": f"korean production gold < floor({GOLD_MERGE_MIN_KOREAN_GOLD}) — 한국어 라벨 충원",
    "merge_gate_not_ready": "MERGE_GATE(precision≥0.98·FPR≤0.01·hard_neg_fp=0·KO≥0.98) 미충족 — calibration 후 재평가",
}


# ── reviewer_id pseudonymization(§5/§10-30 — raw PII 미노출) ──────────────────────────────────────────
def pseudonymize_reviewer_id(reviewer_id: str) -> str:
    """raw reviewer_id → 결정론 pseudonym(공개 report 용). 같은 id → 같은 pseudonym(agreement 집계 가능).

    **암호 보안이 아니라 출력 표면 unlinkability 용**(salt 없음·재현 가능). 저엔트로피 id 공간(이메일/사번)은
    enumeration/사전공격으로 **가역**이다 — "역산 불가"가 아니라 "report 에 raw id 를 직접 싣지 않기 위한 봉인".
    내부 resolve 는 raw id 로 하되, 노출 표면에는 이 해시만 나간다."""
    h = hashlib.sha1(str(reviewer_id).encode("utf-8")).hexdigest()[:12]
    return f"{_REVIEWER_ID_PREFIX}{h}"


# ── 옵션 A: reviewer packet export(score-free labeler view·raw body 0) ────────────────────────────────
def export_reviewer_packet(queue: dict, *, write_path: Optional[Any] = None) -> dict:
    """scored reviewer queue → export 가능 packet + labeler-facing view(score/rationale/predicted_status 0).

    queue 는 `build_near_match_reviewer_queue` 출력(packet_rows 는 이미 validate_labeling_packet 통과). labeler_view 는
    bucket·model 판정 제거(bias 0). write_path 주면 internal ops JSONL(packet_rows) 기록 — 기본 None(파일 미생성)."""
    packet_rows = list(queue.get("packet_rows") or [])
    labeler_view = list(queue.get("labeler_view") or [])
    # labeler-facing view 에 verdict 누출 0 재확인(이중 방어 — queue build 에서 이미 검증).
    leaked = sorted({k for v in labeler_view for k in v if k in FORBIDDEN_LABEL_FIELDS
                     or k in {"sampling_bucket", "score", "rationale", "predicted_status"}})
    if leaked:
        raise ValueError(f"labeler-facing view leaks hidden keys (bias 차단): {leaked}")
    written = 0
    if write_path is not None and packet_rows:
        from backend.app.services.identity_human_labeling import write_labeling_packet_jsonl
        written = write_labeling_packet_jsonl(list(queue.get("packet_items") or []), write_path)
    return {
        "packet_exportable": bool(packet_rows),
        "packet_assignment_count": len(packet_rows),
        "labeler_view_count": len(labeler_view),
        "labeler_view_sample_keys": sorted(labeler_view[0].keys()) if labeler_view else [],
        "score_hidden_from_labeler": True,
        "rationale_hidden_from_labeler": True,
        "labeler_prediction_hidden": True,
        "raw_body_absent": True,        # allowlist(title 헤드라인만).
        "secret_absent": True,          # allowlist 가 api_key/secret 구조적 차단.
        "jsonl_rows_written": written,
    }


# ── 옵션 A/D: reviewer label import(파일 없음 = no_labels·실패 아님) ──────────────────────────────────
def import_reviewer_labels(
    label_path: Optional[Any], *, label_source: str = LABEL_SOURCE_SYNTHETIC
) -> dict:
    """optional real label file → 검증된 ReviewerLabel + 진단. 파일 없음/None → no_labels report(graceful).

    forbidden field(score/rationale/raw body/secret) 누출은 `load_reviewer_labels` allowlist 가 fail-loud 로 거부 —
    여기서 catch 해 block_reason 으로 분류(malformed vs forbidden vs missing). label_source 검증(3-way)."""
    if label_source not in LABEL_SOURCES:
        raise ValueError(f"invalid label_source {label_source!r} (allowed: {sorted(LABEL_SOURCES)})")
    out: dict[str, Any] = {
        "label_import_attempted": label_path is not None,
        "label_file_present": False,
        "label_schema_valid": None,
        "label_source": label_source,
        "labels": [],
        "block_reason": None,
    }
    if label_path is None:
        out["block_reason"] = "no_labels"
        return out
    from pathlib import Path
    p = Path(label_path)
    if not p.exists():
        out["block_reason"] = "label_file_missing"
        return out
    out["label_file_present"] = True
    try:
        labels = load_reviewer_labels(p)
    except ValueError as exc:
        msg = str(exc)
        out["label_schema_valid"] = False
        if "disallowed keys" in msg:
            out["block_reason"] = "forbidden_field_in_label"
        elif "cannot be gold" in msg:        # model/self/LLM label(human-only 위반) — 진단 분리(정직).
            out["block_reason"] = "model_label_rejected"
        else:                                # invalid JSON·enum·길이·중복 등.
            out["block_reason"] = "malformed_label_file"
        out["schema_error"] = msg[:200]   # 메시지(키 이름만)·값 미포함(allowlist 메시지는 secret 비포함).
        return out
    out["label_schema_valid"] = True
    out["labels"] = labels
    if not labels:
        out["block_reason"] = "no_labels"
    return out


# ── 옵션 B: agreement/conflict/adjudication + production/synthetic gold 분리 ───────────────────────────
def resolve_label_operations(
    labels: list[ReviewerLabel], *, adjudications: Optional[dict] = None,
    label_source: str = LABEL_SOURCE_SYNTHETIC,
) -> dict:
    """ReviewerLabel → resolved gold + agreement + conflict queue + **production/synthetic gold 분리**(§6).

    규칙(기존 resolve 재사용): 1명=insufficient · 2+만장일치=agreed(gold) · 2+불일치+human adjudication=adjudicated(gold) ·
    2+불일치=conflict(queue). production gold = **label_source==production AND dataset_source==live_derived** 인 gold 만
    (synthetic/test 는 simulated only — production_gold_count 불변). reviewer_id 는 pseudonym 으로만 노출.

    **human-only gold 불변(cardinal)**: model/self/LLM label 은 gold 가 될 수 없다 — 파일 경로(`load_reviewer_labels`)
    뿐 아니라 이 chokepoint 에서도 fail-loud 로 강제(in-memory `reviewer_labels` 경로가 가드를 우회하지 못하게)."""
    non_human = sorted({lab.reviewer_kind for lab in labels if lab.reviewer_kind != REVIEWER_HUMAN})
    if non_human:
        raise ValueError(
            f"model/self/LLM label cannot be gold — human only "
            f"(reviewer_kind != {REVIEWER_HUMAN!r}): {non_human}")
    resolved = resolve_gold_from_reviewers(labels, adjudications=adjudications)
    agreement = compute_reviewer_agreement(labels)
    conflict_queue = adjudication_queue_from_resolved(resolved)
    gold_pairs = resolved_to_gold_pairs(resolved)

    # ⚠ production_gold 무결성은 **선언 기반**(provenance 미검증) — label_source/dataset_source 는 caller 가 주는
    # 평문 태그라 synthetic 을 live 로 오태깅하면 production gold 로 둔갑 가능. 현 production_gold 0 은 "구조가 막아서"가
    # 아니라 "실 production 실행이 아직 없어서"다(R-IdentityHumanLabeling — 실 reviewer 충원·provenance 바인딩 잔여).
    is_production = label_source == LABEL_SOURCE_PRODUCTION
    production_gold = [g for g in gold_pairs if is_production and g.dataset_source == SOURCE_LIVE]
    synthetic_gold = [g for g in gold_pairs if g not in production_gold]

    # resolution status 카운트(frozen 상수 참조 — 문자열 리터럴 drift 차단).
    single_reviewer = sum(1 for r in resolved if r.resolution_method == RESOLUTION_SINGLE)
    unanimous = sum(1 for r in resolved if r.agreement_status == AGREE_AGREED)
    conflict = sum(1 for r in resolved if r.agreement_status == AGREE_CONFLICT)
    adjudicated = sum(1 for r in resolved if r.agreement_status == AGREE_ADJUDICATED)

    distinct_reviewers = {lab.reviewer_id for lab in labels}
    pseudonymous_reviewers = sorted({pseudonymize_reviewer_id(r) for r in distinct_reviewers})

    return {
        "resolved": resolved,
        "agreement": agreement,
        "conflict_adjudication_queue": conflict_queue,
        "production_gold": production_gold,
        "synthetic_gold": synthetic_gold,
        "label_count": len(labels),
        "reviewer_count": len(distinct_reviewers),
        "pseudonymous_reviewers": pseudonymous_reviewers,   # raw reviewer_id 미노출(PII).
        "single_reviewer_count": single_reviewer,
        "unanimous_count": unanimous,
        "conflict_count": conflict,
        "adjudicated_count": adjudicated,
        "production_gold_count": len(production_gold),
        "synthetic_gold_count": len(synthetic_gold),
        "gold_ready": bool(production_gold),       # 실 production gold 있을 때만 True(synthetic→False·정직).
        "merge_allowed": False,
        "no_merge_without_gold": True,
    }


# ── 옵션 C: gold calibration preflight(§7 — denominator readiness·top_k bias·korean·MERGE_GATE) ────────
def build_calibration_preflight(
    resolve_result: dict, *, hard_negative_count: int = 0, top_k_sourced: bool = True,
) -> dict:
    """production gold → MERGE_GATE calibration readiness(§7). gold 없으면 모든 readiness False(정직).

    gold 가 없거나 부족하면 calibration_ready/merge_gate_ready False. top_k_sourced=True 면 scorer top-k 표집 편향
    경고(positive-lean) — gold 표집을 score 로 편향시키지 않도록 hard negative 동시 표집 필요. embedding/LLM threshold 는
    이 preflight 가 Ready 가 되기 전까지 확정 금지."""
    production_gold: list[GoldPair] = list(resolve_result.get("production_gold") or [])
    n = len(production_gold)
    positive = sum(1 for g in production_gold if g.label == LABEL_SAME)
    negative = sum(1 for g in production_gold if g.label == LABEL_DIFFERENT)
    korean = sum(1 for g in production_gold if g.language == "ko")

    lang_dist: dict[str, int] = {}
    pair_dist: dict[str, int] = {}
    for g in production_gold:
        lang_dist[g.language] = lang_dist.get(g.language, 0) + 1
        key = "|".join(sorted((g.source_type_left, g.source_type_right)))
        pair_dist[key] = pair_dist.get(key, 0) + 1

    # MERGE_GATE + 표본 floor(live_derived gold only — synthetic 은 evaluate_gold_merge_readiness 가 자동 배제).
    readiness = evaluate_gold_merge_readiness(production_gold)

    agreement = resolve_result.get("agreement") or {}
    multi = agreement.get("multi_reviewer_pairs", 0) or 0
    conflict_rate = round(resolve_result.get("conflict_count", 0) / multi, 4) if multi else None

    pn_min, pn_max = (min(positive, negative), max(positive, negative))
    balance_ratio = round(pn_min / pn_max, 4) if pn_max else None

    precision_denominator_ready = n >= GOLD_MERGE_MIN_LIVE_GOLD
    fpr_denominator_ready = n >= GOLD_MERGE_MIN_LIVE_GOLD and negative > 0
    korean_ready = korean >= GOLD_MERGE_MIN_KOREAN_GOLD
    calibration_ready = bool(
        precision_denominator_ready and fpr_denominator_ready and korean_ready
        and positive > 0 and negative > 0)

    return {
        "production_gold_count": n,
        "positive_gold_count": positive,
        "negative_gold_count": negative,
        "korean_gold_count": korean,
        "language_distribution": dict(sorted(lang_dist.items())),
        "source_pair_distribution": dict(sorted(pair_dist.items())),
        "reviewer_count": resolve_result.get("reviewer_count", 0),
        "agreement_rate": agreement.get("agreement_rate"),
        "conflict_rate": conflict_rate,
        "positive_negative_balance": {
            "positive": positive, "negative": negative, "ratio": balance_ratio,
            "balanced": bool(balance_ratio is not None and balance_ratio >= 0.5),
        },
        "hard_negative_coverage": {
            "count": hard_negative_count,
            # 통계 음성 floor 미충족(연습 표본 수준) — gold 음성도 부족.
            "sufficient": False,
        },
        # scorer top-k 는 same-event-lean → gold 표집을 positive 로 편향(R-GoldSamplingBias). 항상 경고(정직).
        "top_k_bias_warning": bool(top_k_sourced),
        "korean_calibration_ready": korean_ready,
        "precision_denominator_ready": precision_denominator_ready,
        "fpr_denominator_ready": fpr_denominator_ready,
        "min_live_gold": GOLD_MERGE_MIN_LIVE_GOLD,
        "min_korean_gold": GOLD_MERGE_MIN_KOREAN_GOLD,
        "merge_gate": {k: readiness[k] for k in (
            "precision_ok", "fpr_ok", "hard_negative_fp_ok", "korean_precision_ok", "passed")},
        "calibration_ready": calibration_ready,
        # MERGE_GATE 충족 + 표본 floor 충족이어야 ready(evaluate_gold_merge_readiness.merge_ready). gold 0 → False.
        "merge_gate_ready": bool(readiness.get("merge_ready")),
        "merge_gate_thresholds": {
            "precision_min": MERGE_GATE["likely_same_precision_min"],
            "fpr_max": MERGE_GATE["likely_same_false_positive_rate_max"],
            "hard_negative_fp_max": MERGE_GATE["hard_negative_false_positive_max"],
            "korean_precision_min": MERGE_GATE["korean_subset_precision_min"],
        },
        "auto_merge_enabled": False,
    }


# ── §4: 통합 운영 entrypoint ──────────────────────────────────────────────────────────────────────────
def run_reviewer_label_operations(
    *, queue: Optional[dict] = None, discovery: Optional[dict] = None,
    label_path: Optional[Any] = None, reviewer_labels: Optional[list[ReviewerLabel]] = None,
    adjudications: Optional[dict] = None, label_source: str = LABEL_SOURCE_SYNTHETIC,
    packet_id: str = "reviewer_ops_pkt", reviewers: Optional[list[str]] = None,
    write_packet_path: Optional[Any] = None, top_k_sourced: bool = True,
) -> dict:
    """scored reviewer queue + (optional) reviewer labels → §4 운영 output(병합 0·LLM 0·embedding 0·DB 0).

    queue(=build_near_match_reviewer_queue 출력) 직접 전달 또는 discovery 로 build. reviewer_labels(in-memory) 또는
    label_path(파일) 중 하나로 라벨 주입 — 둘 다 없으면 no_labels(정직). production gold 는 label_source==production &
    live_derived 일 때만 카운트. 어떤 경로도 merge/LLM/embedding/DB 를 건드리지 않는다."""
    if queue is None and discovery is not None:
        queue = build_near_match_reviewer_queue(discovery, packet_id=packet_id, reviewers=reviewers)
    queue = queue or {}
    block_reasons: list[str] = []

    export = export_reviewer_packet(queue, write_path=write_packet_path)
    if not export["packet_exportable"]:
        block_reasons.append("no_packet")

    # 라벨 주입: in-memory(typed) 우선, 없으면 파일 import.
    if reviewer_labels is not None:
        if label_source not in LABEL_SOURCES:
            raise ValueError(f"invalid label_source {label_source!r}")
        # human-only gold 불변(cardinal): in-memory 경로도 reviewer_kind 가드(파일 경로 `_validate_reviewer_row`
        # 와 대칭). model/self/LLM label 은 gold 후보가 아니므로 거부→block_reason(crash 아닌 graceful·gold 0).
        non_human = bool(any(lab.reviewer_kind != REVIEWER_HUMAN for lab in reviewer_labels))
        import_info = {
            "label_import_attempted": True, "label_file_present": False,
            "label_schema_valid": not non_human, "label_source": label_source,
            "labels": [] if non_human else list(reviewer_labels),
            "block_reason": "model_label_rejected" if non_human else None,
        }
    else:
        import_info = import_reviewer_labels(label_path, label_source=label_source)
    labels: list[ReviewerLabel] = list(import_info.get("labels") or [])
    if import_info.get("block_reason"):
        block_reasons.append(import_info["block_reason"])

    if labels:
        resolve_result = resolve_label_operations(
            labels, adjudications=adjudications, label_source=label_source)
        if label_source != LABEL_SOURCE_PRODUCTION:
            block_reasons.append("no_production_labels")
    else:
        resolve_result = {
            "production_gold": [], "synthetic_gold": [], "label_count": 0, "reviewer_count": 0,
            "pseudonymous_reviewers": [], "single_reviewer_count": 0, "unanimous_count": 0,
            "conflict_count": 0, "adjudicated_count": 0, "production_gold_count": 0,
            "synthetic_gold_count": 0, "gold_ready": False,
            "agreement": {"agreement_rate": None, "multi_reviewer_pairs": 0},
            "conflict_adjudication_queue": [],
        }

    hard_negative_count = (
        queue.get("hard_negative_discovery_count", 0) + queue.get("hard_negative_synthetic_count", 0))
    preflight = build_calibration_preflight(
        resolve_result, hard_negative_count=hard_negative_count, top_k_sourced=top_k_sourced)

    # block reasons(calibration).
    if resolve_result["production_gold_count"] < GOLD_MERGE_MIN_LIVE_GOLD:
        block_reasons.append("insufficient_gold_for_calibration")
    if not preflight["merge_gate_ready"]:
        block_reasons.append("merge_gate_not_ready")

    agreement_ready = bool(
        label_source == LABEL_SOURCE_PRODUCTION
        and (resolve_result.get("agreement") or {}).get("multi_reviewer_pairs", 0) > 0)

    next_actions = [_NEXT_ACTION.get(br, f"investigate: {br}") for br in dict.fromkeys(block_reasons)]

    return {
        "operation_name": OPERATION_NAME,
        "packet_id": packet_id,
        "packet_source": "near_match_reviewer_queue(semantic scorer top-k)" if top_k_sourced else "discovery",
        "packet_exportable": export["packet_exportable"],
        "packet_assignment_count": export["packet_assignment_count"],
        "labeler_view_sample_keys": export["labeler_view_sample_keys"],
        "label_import_attempted": import_info.get("label_import_attempted", False),
        "label_file_present": import_info.get("label_file_present", False),
        "label_schema_valid": import_info.get("label_schema_valid"),
        "label_source": label_source,
        "labeler_prediction_hidden": export["labeler_prediction_hidden"],
        "score_hidden_from_labeler": export["score_hidden_from_labeler"],
        "rationale_hidden_from_labeler": export["rationale_hidden_from_labeler"],
        "raw_body_absent": export["raw_body_absent"],
        "secret_absent": export["secret_absent"],
        "reviewer_count": resolve_result["reviewer_count"],
        "pseudonymous_reviewers": resolve_result["pseudonymous_reviewers"],
        "label_count": resolve_result["label_count"],
        "single_reviewer_count": resolve_result["single_reviewer_count"],
        "unanimous_count": resolve_result["unanimous_count"],
        "conflict_count": resolve_result["conflict_count"],
        "adjudicated_count": resolve_result["adjudicated_count"],
        "conflict_adjudication_queue": resolve_result["conflict_adjudication_queue"],
        "production_gold_count": resolve_result["production_gold_count"],
        "synthetic_gold_count": resolve_result["synthetic_gold_count"],
        "gold_ready": resolve_result["gold_ready"],
        "agreement_ready": agreement_ready,
        "agreement_rate": (resolve_result.get("agreement") or {}).get("agreement_rate"),
        "calibration_ready": preflight["calibration_ready"],
        "calibration_preflight": preflight,
        "merge_gate_ready": preflight["merge_gate_ready"],
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "db_write": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "agent_contract": REVIEWER_OPS_AGENT_CONTRACT,
        "block_reasons": list(dict.fromkeys(block_reasons)),
        "next_actions": next_actions,
    }


# ── CLI(기본 captured fixture·network 0·DB 0·라벨 없음=no_labels 정직; synthetic 라벨 데모 opt-in) ─────
def _demo_synthetic_labels() -> list[ReviewerLabel]:
    """경로 검증용 synthetic reviewer label(2인 만장일치 1·conflict 1) — **synthetic_fixture**(production gold 0)."""
    def _lab(pid: str, rid: str, label: str) -> ReviewerLabel:
        return ReviewerLabel(
            pair_id=pid, reviewer_id=rid, review_round=1, label=label, label_confidence="medium",
            reviewed_at="2026-06-22T00:00:00+00:00", language="en",
            source_type_left="article", source_type_right="article",
            title_left="demo headline left", title_right="demo headline right",
            observed_at_left="2026-06-22", observed_at_right="2026-06-22",
            dataset_source=SOURCE_SYNTHETIC)
    return [
        _lab("hn_syn:quake", "reviewer_a", "different_event"),
        _lab("hn_syn:quake", "reviewer_b", "different_event"),   # 만장일치 → simulated gold(production 아님)
        _lab("hn_syn:rate", "reviewer_a", "same_event"),
        _lab("hn_syn:rate", "reviewer_b", "different_event"),    # conflict → adjudication queue
    ]


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="reviewer label operations + gold calibration preflight (ADR#66·병합 0·LLM 0·DB 0).")
    parser.add_argument("--synthetic-labels", action="store_true",
                        help="synthetic reviewer label 데모(경로 검증·production gold 0·synthetic_fixture).")
    parser.add_argument("--synthetic-hard-negatives", action="store_true",
                        help="trap-zone synthetic hard negative 포함(calibration 연습).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from backend.app.tools.source_overlap_discovery import (
        build_captured_overlap_fixture,
        discover_overlap,
    )
    disc = discover_overlap(build_captured_overlap_fixture())
    queue = build_near_match_reviewer_queue(
        disc, packet_id="reviewer_ops_cli",
        include_synthetic_hard_negatives=ns.synthetic_hard_negatives)
    labels = _demo_synthetic_labels() if ns.synthetic_labels else None
    out = run_reviewer_label_operations(
        queue=queue, reviewer_labels=labels, label_source=LABEL_SOURCE_SYNTHETIC,
        packet_id="reviewer_ops_cli", top_k_sourced=False)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} packet_exportable={out['packet_exportable']} "
          f"assignments={out['packet_assignment_count']}")
    print(f"- labels: import_attempted={out['label_import_attempted']} count={out['label_count']} "
          f"reviewers={out['reviewer_count']} source={out['label_source']}")
    print(f"- resolution: single={out['single_reviewer_count']} unanimous={out['unanimous_count']} "
          f"conflict={out['conflict_count']} adjudicated={out['adjudicated_count']}")
    print(f"- gold: production={out['production_gold_count']} synthetic={out['synthetic_gold_count']} "
          f"gold_ready={out['gold_ready']}")
    print(f"- calibration: calibration_ready={out['calibration_ready']} merge_gate_ready={out['merge_gate_ready']} "
          f"top_k_bias_warning={out['calibration_preflight']['top_k_bias_warning']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} no_merge_without_gold={out['no_merge_without_gold']} "
          f"db_write={out['db_write']} llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']}")
    print(f"- labeler_view_keys (no score/bucket/predicted): {out['labeler_view_sample_keys']}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
