"""ADR#59 — near-match reviewer/gold queue operationalization (병합 0·LLM 0·predicted_status 숨김).

ADR#58 이 정직하게 드러낸 한계: untargeted RSS fetch 는 same-event cross-source overlap 을 거의 만들지
못하고(55 record→overlap 0), deterministic fingerprint 는 paraphrase(다른 매체의 같은 사건 재보도)를 못 잡는다
(near_match_below_fingerprint). 그 paraphrase 후보를 **버리지도 병합하지도 않고** 기존 human-labeling/gold/
MERGE_GATE 머신으로 보내는 **운영 가능한 reviewer/gold queue** 가 이 모듈이다.

이 모듈은 재구현하지 않는다 — 오케스트레이터다. 무거운 일은 전부 기존 단일 출처가 한다:
  - near-positive 후보 생성: `source_overlap_discovery.build_near_match_reviewer_candidates`
  - hard-negative 후보 생성: `source_overlap_discovery.build_hard_negative_reviewer_candidates`(측정 기반) +
    `build_synthetic_hard_negative_candidates`(trap-zone calibration·**synthetic_fixture 명시**)
  - packet 샘플링/배정/검증: `identity_human_labeling.build_labeling_packet`/`validate_labeling_packet`
  - labeler-facing view: `identity_human_labeling.labeler_facing_view`(bucket·model 판정 제거)
  - gold 승격/agreement/conflict: `resolve_gold_from_reviewers`/`resolved_to_gold_pairs`/
    `adjudication_queue_from_resolved`/`compute_reviewer_agreement`

절대 불변(상용 안전 계약):
  - **no merge / no auto-merge**: 같은 사건 단정·병합 0(no_merge_without_gold/no_merge_without_gate 불변).
  - **predicted_status 숨김**: near/hard 후보는 predicted_status/score/verdict 미포함(bias 차단). packet 은
    `_PACKET_FORBIDDEN_VERDICT_KEYS` 로 이중 차단·`validate_labeling_packet` fail-loud.
  - **no public Intelligence Unit**: curated IU 생성 0(미구축).
  - **source role guard**: publishable core(official/article)×publishable 만 reviewer 후보. community(reaction)/
    market(signal)/catalog(enrichment) 는 anchor 금지(source_overlap_discovery 가 필터·여기서 재확인).
  - **LLM/embedding 호출 0**: queue 전 과정 결정론. embedding/LLM adjudicator 는 No-Go 인터페이스 문서화만
    (`EMBEDDING_LLM_ADJUDICATOR_INTERFACE`·gold/MERGE_GATE 미충족).
  - **본문 미저장**: title 헤드라인(≤512)·canonical·observed_at·source_type 만(raw body/PII 0).
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Optional

from backend.app.services.identity_eval_dataset import LANGUAGES, SOURCE_TYPES
from backend.app.services.identity_human_labeling import (
    DEFAULT_REVIEWERS_PER_PAIR,
    SELECTION_PAIR_ID_ORDER,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    adjudication_queue_from_resolved,
    build_labeling_packet,
    compute_reviewer_agreement,
    labeler_facing_view,
    packet_item_to_dict,
    resolve_gold_from_reviewers,
    resolved_to_gold_pairs,
    validate_labeling_packet,
)
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    build_hard_negative_reviewer_candidates,
    build_near_match_reviewer_candidates,
    discover_overlap,
)

# 후보 provenance(정직 — synthetic 을 real 로 위장 금지).
PROVENANCE_DISCOVERY = "discovery_derived"     # 실/captured record 의 pairwise scan 에서 측정.
PROVENANCE_SYNTHETIC = "synthetic_fixture"     # trap-zone calibration fixture(실 source 아님·명시).

# 기본 reviewer slot(placeholder — **실 human 아님**·gold_ready 는 실 label 전까지 False). distinct ≥ 2(agreement 요건).
_PLACEHOLDER_REVIEWERS = ["reviewer_pool_slot_a", "reviewer_pool_slot_b"]

# §7 embedding/LLM adjudicator 인터페이스 — **No-Go**(gold/MERGE_GATE 미충족·이번 턴 호출 0). 설계만 고정.
EMBEDDING_LLM_ADJUDICATOR_INTERFACE = {
    "input": (
        "near_match reviewer candidate(title_left/right·source_type·observed_at·canonical — raw body 미포함)"),
    "output": "provisional_score(0..1) ONLY — merge 결정 아님·label 아님·같은 사건 단정 아님",
    "requires": [
        "gold_calibration(live-derived gold ≥ floor — 현재 0)",
        "MERGE_GATE(likely_same precision≥0.98·FPR≤0.01·hard_negative_fp=0·korean precision≥0.98)",
        "adversarial 승인(false-merge=cardinal sin)",
    ],
    "seam": "semantic_identity_adjudicator.AdjudicationFeatures.semantic_score (현재 None·미배선)",
    "status": "No-Go (gold/MERGE_GATE 미충족 — 이번 턴 LLM/embedding 호출 0)",
    "forbidden": [
        "같은 사건 단정", "merge 실행", "public Intelligence Unit 생성", "gold 없이 calibration 주장",
        "community/market/catalog 를 event anchor 로 사용",
    ],
}


# ── synthetic hard negatives(trap-zone calibration·**synthetic_fixture 명시**·실 source 아님) ──────────
def build_synthetic_hard_negative_candidates() -> list[dict]:
    """trap-zone hard negative — **어휘는 매우 유사하나 명백히 다른 사건**(같은 날·같은 템플릿·다른 entity).

    reviewer 가 "비슷해 보여도 다른 사건"을 보정(calibration)하도록 **음성 calibration substrate** 를 제공한다(통계
    음성 floor[수백] 충족이 **아니라** reviewer 연습용 소량). deterministic fingerprint overlap 0 환경(real RSS)에서도
    reviewer agreement 연습 표본을 확보하는 용도. **synthetic_fixture**(실 source behavior 아님·라벨은 reviewer 가·
    같은 사건 단정 0). publishable×publishable(article) 만."""
    day = "2026-06-22"

    def _pair(pid: str, ta: str, tb: str) -> dict:
        return {
            "pair_id": f"hn_syn:{pid}",
            "label": "unlabeled",
            "language": "und",
            "source_type_left": "article", "source_type_right": "article",
            "title_left": ta, "title_right": tb,
            "observed_at_left": day, "observed_at_right": day,
            "canonical_url_left": f"https://outlet-syn-a.test/{pid}",
            "canonical_url_right": f"https://outlet-syn-b.test/{pid}",
            "title_token_jaccard": None,       # synthetic — 측정 jaccard 아님(report 가 provenance 로 분리).
            "date_bucket_match": True,
            "risk_tags": ["hard_negative"],
            "reason": "synthetic_trap_zone(어휘 유사·다른 사건·calibration — reviewer 확인 필요)",
            "no_merge_without_gold": True,
        }

    return [
        # 같은 템플릿·다른 지진(다른 규모·다른 지역) — 어휘 거의 동일하나 다른 사건.
        _pair("quake", "Magnitude 6.1 earthquake strikes northern coast region",
              "Magnitude 5.4 earthquake strikes southern coast region"),
        # 같은 템플릿·반대 결정 — 중앙은행 인상 vs 동결.
        _pair("rate", "Central bank raises benchmark interest rate by 25 basis points",
              "Central bank holds benchmark interest rate unchanged this month"),
        # 같은 템플릿·다른 안건 — 시의회 주택 승인 vs 경기장 부결.
        _pair("council", "City council approves new downtown affordable housing project",
              "City council rejects new downtown sports stadium project"),
    ]


# ── near/hard 후보 → packet 호환 worksheet row 정규화(language und→unknown·observed None→''·title str≤512) ──
def _to_worksheet_row(candidate: dict, *, dataset_source: str) -> dict:
    """near/hard reviewer candidate → `build_labeling_packet` 호환 worksheet row.

    packet 경계 계약을 보장: language ∈ {ko,en,mixed,unknown}(und→unknown)·source_type ∈ SOURCE_TYPES·title str≤512·
    observed_at None→''. predicted_status/score 는 **미포함 유지**(bias 차단). `dataset_source`(live_derived/
    synthetic_fixture)를 명시 부여 — 미래 `summarize_packet_sampling`(기본값 live)에 이 행이 흘러가도 synthetic 이
    live 표본으로 오집계되지 않도록 봉인(honesty). title_token_jaccard/date_bucket_match/no_merge_without_gold/
    dataset_source 는 extra(packet 변환 시 _packet_item 이 allowlist drop·queue/report 의 provenance·uncertainty 보존용)."""
    lang = candidate.get("language") or "unknown"
    if lang not in LANGUAGES:
        lang = "unknown"

    def _st(v: Any) -> str:
        return v if v in SOURCE_TYPES else "unknown"

    def _title(v: Any) -> str:
        return (str(v) if v is not None else "")[:512]

    return {
        "pair_id": str(candidate["pair_id"]),
        "label": "unlabeled",
        "language": lang,
        "source_type_left": _st(candidate.get("source_type_left")),
        "source_type_right": _st(candidate.get("source_type_right")),
        "title_left": _title(candidate.get("title_left")),
        "title_right": _title(candidate.get("title_right")),
        "observed_at_left": candidate.get("observed_at_left") or "",
        "observed_at_right": candidate.get("observed_at_right") or "",
        "canonical_url_left": candidate.get("canonical_url_left"),
        "canonical_url_right": candidate.get("canonical_url_right"),
        "risk_tags": list(candidate.get("risk_tags") or []),
        "reason": str(candidate.get("reason", "")),
        # extra(packet drop·report provenance/uncertainty 보존):
        "dataset_source": dataset_source,
        "title_token_jaccard": candidate.get("title_token_jaccard"),
        "date_bucket_match": candidate.get("date_bucket_match"),
        "no_merge_without_gold": True,
    }


# ── §4/§5: near-match reviewer queue 조립(near positive + hard negative → 검증된 packet) ──────────────
def build_near_match_reviewer_queue(
    discovery: dict, *, packet_id: str = "near_match_pkt",
    reviewers: Optional[list[str]] = None,
    include_hard_negatives: bool = True,
    include_synthetic_hard_negatives: bool = False,
    reviewers_per_pair: int = DEFAULT_REVIEWERS_PER_PAIR,
    selection_method: str = SELECTION_PAIR_ID_ORDER,
) -> dict:
    """discovery → near-positive(paraphrase) + hard-negative 를 묶어 **검증된 reviewer labeling packet** 으로.

    near positive 와 hard negative 를 **함께** 샘플링(reviewer 가 same/different 를 보정 가능·음성 floor 충당).
    predicted_status 미포함·LLM 0·merge 0. `build_labeling_packet`(bucket 샘플링·reviewer 배정·model 판정 차폐)을
    그대로 호출하고 `validate_labeling_packet`(verdict 누출/allowlist/enum fail-loud)로 잠근다. 반환은 packet items
    /labeler-facing view/provenance 카운트. reviewers 미지정 시 placeholder slot(실 human 아님·gold_ready False)."""
    reviewers = reviewers or list(_PLACEHOLDER_REVIEWERS)
    near = build_near_match_reviewer_candidates(discovery)
    hard_disc = build_hard_negative_reviewer_candidates(discovery) if include_hard_negatives else []
    hard_syn = build_synthetic_hard_negative_candidates() if include_synthetic_hard_negatives else []

    # provenance(honesty): discovery 가 실 fetch 면 live_derived·captured fixture 면 synthetic_fixture.
    # synthetic hard negative 는 항상 synthetic_fixture(실 source behavior 아님).
    disc_source = SOURCE_LIVE if discovery.get("real_fetch") else SOURCE_SYNTHETIC
    rows_near = [_to_worksheet_row(c, dataset_source=disc_source) for c in near]
    rows_hard_disc = [_to_worksheet_row(c, dataset_source=disc_source) for c in hard_disc]
    rows_hard_syn = [_to_worksheet_row(c, dataset_source=SOURCE_SYNTHETIC) for c in hard_syn]
    worksheet = rows_near + rows_hard_disc + rows_hard_syn

    if worksheet:
        items = build_labeling_packet(
            worksheet, packet_id=packet_id, reviewers=reviewers,
            reviewers_per_pair=reviewers_per_pair, selection_method=selection_method)
    else:
        items = []
    packet_rows = [packet_item_to_dict(it) for it in items]
    validate_labeling_packet(packet_rows)   # fail-loud: predicted_status/score/reason/label 누출·raw body 차단.
    labeler_view = [labeler_facing_view(it) for it in items]

    distinct_pairs = sorted({r["pair_id"] for r in worksheet})
    return {
        "packet_id": packet_id,
        "packet_items": items,            # LabelingPacketItem(내부 ops·sampling_bucket 포함)
        "packet_rows": packet_rows,       # 검증된 dict(ops artifact)
        "labeler_view": labeler_view,     # reviewer-facing(bucket·model 판정 제거 — bias 0)
        "worksheet_rows": worksheet,      # near+hard 정규화 행(uncertainty 보존)
        "queue_pair_ids": distinct_pairs,
        "near_positive_count": len(rows_near),
        "hard_negative_discovery_count": len(rows_hard_disc),
        "hard_negative_synthetic_count": len(rows_hard_syn),
        "reviewers": list(dict.fromkeys(reviewers)),
        "reviewers_per_pair": reviewers_per_pair,
        "llm_invoked": False,
        "no_merge_without_gold": True,
        "no_merge_without_gate": True,
        "no_public_intelligence_unit": True,
    }


# ── §5: gold-seed report(queue 통계·labeler prediction 숨김·gold_ready·merge_allowed False) ───────────
def build_gold_seed_report(discovery: dict, queue: dict, *, resolved_gold: Any = None) -> dict:
    """§5 필수 fields — queue/near/hard 카운트·source_role·bucket 분포·reviewer_packet_exportable·labeler_prediction
    _hidden·gold_ready(실 gold pair 있을 때만)·merge_allowed=False·no_merge_without_gold=True. write-free."""
    packet_rows = queue.get("packet_rows") or []
    bucket_dist: dict[str, int] = {}
    role_dist: dict[str, int] = {}
    for r in packet_rows:
        bucket_dist[r["sampling_bucket"]] = bucket_dist.get(r["sampling_bucket"], 0) + 1
        for side in ("source_type_left", "source_type_right"):
            role_dist[r[side]] = role_dist.get(r[side], 0) + 1
    jaccards = [
        w["title_token_jaccard"] for w in queue.get("worksheet_rows") or []
        if isinstance(w.get("title_token_jaccard"), (int, float))]
    hard_total = queue.get("hard_negative_discovery_count", 0) + queue.get("hard_negative_synthetic_count", 0)
    gold_pairs = list(resolved_gold or [])
    return {
        "queue_size": len(queue.get("queue_pair_ids") or []),
        "packet_assignment_count": len(packet_rows),
        "near_match_count": queue.get("near_positive_count", 0),
        "hard_negative_count": hard_total,
        "hard_negative_discovery_count": queue.get("hard_negative_discovery_count", 0),
        "hard_negative_synthetic_count": queue.get("hard_negative_synthetic_count", 0),
        "fingerprint_overlap_count": discovery.get("fingerprint_overlap_pairs", 0),
        "source_role_distribution": dict(sorted(role_dist.items())),
        "bucket_distribution": dict(sorted(bucket_dist.items())),
        "uncertainty": {
            "measured_jaccard_count": len(jaccards),
            "min_title_token_jaccard": round(min(jaccards), 4) if jaccards else None,
            "max_title_token_jaccard": round(max(jaccards), 4) if jaccards else None,
        },
        "reviewer_packet_exportable": bool(packet_rows),
        "labeler_prediction_hidden": True,           # validate_labeling_packet 가 구조적 강제(predicted_status 누출 0).
        "raw_body_included": False,                  # title 헤드라인만(allowlist).
        "gold_ready": bool(gold_pairs),              # 실 gold pair 있을 때만 True(실 reviewer label 전까지 False).
        "gold_pair_count": len(gold_pairs),
        "merge_allowed": False,
        "no_merge_without_gold": True,
    }


# ── §5(gold/agreement/conflict 경로 connector) — resolve_gold_from_reviewers 재사용·thin ─────────────
def resolve_queue_gold(reviewer_labels: list, *, adjudications: Optional[dict] = None) -> dict:
    """packet 라벨(ReviewerLabel) → gold 승격 + conflict adjudication queue + reviewer agreement(기존 머신 재사용).

    실 reviewer label 이 들어오면 ① 2+ 동일→gold ② 2+ 상충+사람 adjudication→gold ③ 2+ 상충 무 adjudication→
    conflict(human-only queue) ④ 1명→insufficient. **gold_ready=실 gold pair 존재 시만**(빈 입력→False=정직).
    merge 는 절대 안 함(gold 는 metric/문서 전용·auto_merge_enabled=False 불변)."""
    resolved = resolve_gold_from_reviewers(reviewer_labels, adjudications=adjudications)
    gold = resolved_to_gold_pairs(resolved)
    conflicts = adjudication_queue_from_resolved(resolved)
    agreement = compute_reviewer_agreement(reviewer_labels)
    return {
        "resolved": resolved,
        "gold_pairs": gold,
        "gold_count": len(gold),
        "conflict_adjudication_queue": conflicts,
        "conflict_count": len(conflicts),
        "reviewer_agreement": agreement,
        "gold_ready": bool(gold),
        "merge_allowed": False,
        "no_merge_without_gate": True,
    }


# ── §8: source acquisition linkage(near_match_yield/reviewer/gold/hard_negative value·목적 기반 수집 전환) ──
def build_reviewer_queue_acquisition_linkage(discovery: dict, queue: dict) -> dict:
    """measured overlap_potential_matrix → source-pair 별 reviewer/gold value 로 **수집을 목적 기반으로 전환**.

    단순 수집량이 아니라 gold/MERGE_GATE 에 가치 있는 후보(near positive=gold seed·hard negative=음성 floor)를 모으는
    방향으로 acquisition 을 steer. topic/keyword 는 LLM/Agent 영역(미배선). 병합·단정 0(no_merge_without_gate)."""
    matrix = discovery.get("overlap_potential_matrix") or []
    pairs: list[dict] = []
    for m in matrix:
        near = m.get("near_match_overlap", 0)
        fp = m.get("fingerprint_overlap", 0)
        hn = m.get("hard_negative_overlap", 0)
        near_yield = "high" if near > 0 else "none"
        reviewer_value = "high" if near > 0 else ("low" if hn > 0 else "none")
        gold_value = "high" if near > 0 else "none"          # near positive → gold seed 후보.
        hard_negative_value = "high" if hn > 0 else "none"   # hard negative → 음성 floor 충당.
        paraphrase_risk = "high" if near > 0 else "low"      # paraphrase 사각지대 위험(deterministic 미검출).
        # priority: near positive 있는 pair 최우선(gold seed) > hard negative 만(음성 floor) > overlap 무.
        priority = 0 if near > 0 else (1 if hn > 0 else 2)
        pairs.append({
            "source_pair": m["source_pair"],
            "near_match_yield_potential": near_yield,
            "reviewer_value": reviewer_value,
            "gold_value": gold_value,
            "hard_negative_value": hard_negative_value,
            "paraphrase_risk": paraphrase_risk,
            "fingerprint_detectable": fp > 0,
            "source_pair_priority": priority,
        })
    pairs.sort(key=lambda p: (p["source_pair_priority"], p["source_pair"]))
    near_total = discovery.get("near_match_below_fingerprint_pairs", 0)
    hard_total = discovery.get("hard_negative_band_pairs", 0)
    return {
        "source_pair_acquisition": pairs,
        "topic_window_priority": {
            "topics": [],   # 결정론 단계 미산출 — watch topic/keyword 는 LLM/Agent 영역(미배선).
            "note": "watch topic/keyword 는 LLM/Agent 영역(미배선) — 결정론 substrate 만 제공.",
        },
        "next_fetch_plan": (
            "near-match yield 있는 source pair 우선 targeted 재수집(same topic/time window) → reviewer/gold seed 충당"
            if near_total > 0 else
            ("hard-negative band 만 존재 → 음성 floor 는 충당되나 same-event 후보 부족 → targeted topic/time 수집 필요"
             if hard_total > 0 else
             "overlap 무 → targeted same-event acquisition(source pair/topic/time window) 필요 — untargeted 수집 중단")),
        "goal": "raw volume → gold/MERGE_GATE value 기반 acquisition 전환(near positive=gold seed·hard negative=음성 floor)",
        "no_merge_without_gate": True,
    }


# ── §7: Agent orchestration schema 보강(reviewer queue planning·embedding/LLM No-Go·merge 불가) ───────
def augment_agent_schema_with_reviewer_queue(
    base_schema: dict, queue: dict, report: dict, linkage: dict,
) -> dict:
    """base agent schema(source_overlap_discovery) + reviewer queue planning 보강. Agent 는 near_match_queue/
    reviewer packet/hard negative/gold value 를 **계획**할 수 있으나 merge·같은 사건 단정·public IU 생성은 불가."""
    near = report.get("near_match_count", 0)
    hard = report.get("hard_negative_count", 0)
    return {
        **base_schema,
        "near_match_queue_priority": "high" if near > 0 else "none",
        "reviewer_packet_priority": "high" if report.get("reviewer_packet_exportable") else "none",
        "hard_negative_sampling_plan": {
            "hard_negative_count": hard,
            "discovery_derived": report.get("hard_negative_discovery_count", 0),
            "synthetic_fixture": report.get("hard_negative_synthetic_count", 0),
            "purpose": "음성 calibration substrate(통계 floor 충족 아님)·reviewer 연습(same/different 보정)·라벨은 reviewer 가",
        },
        "expected_gold_value": "near positive → gold seed(라벨 후 GoldPair)" if near > 0 else "none(near positive 0)",
        "expected_merge_gate_value": (
            "gold 충족 시 MERGE_GATE 평가 substrate(precision/FPR/hard_neg_fp) — 현재 gold 0·미평가"),
        "reviewer_queue_next_fetch_plan": linkage.get("next_fetch_plan"),
        "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go(이번 턴 호출 0).
        "no_merge_without_gate": True,
        "llm_invoked": False,
    }


# ── CLI(기본 captured fixture·network 0·deterministic; synthetic hard negative opt-in) ────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="near-match reviewer/gold queue (ADR#59·병합 0·LLM 0·predicted_status 숨김; 기본 captured fixture).")
    parser.add_argument("--synthetic-hard-negatives", action="store_true",
                        help="trap-zone synthetic hard negative 포함(calibration·synthetic_fixture 명시).")
    parser.add_argument("--no-hard-negatives", action="store_true",
                        help="discovery-derived hard negative 제외(near positive 만).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from backend.app.tools.source_overlap_discovery import build_agent_orchestration_schema

    records = build_captured_overlap_fixture()
    disc = discover_overlap(records)
    queue = build_near_match_reviewer_queue(
        disc, include_hard_negatives=not ns.no_hard_negatives,
        include_synthetic_hard_negatives=ns.synthetic_hard_negatives)
    report = build_gold_seed_report(disc, queue)
    linkage = build_reviewer_queue_acquisition_linkage(disc, queue)
    base_schema = build_agent_orchestration_schema(disc)
    agent_schema = augment_agent_schema_with_reviewer_queue(base_schema, queue, report, linkage)

    print(f"- queue: size={report['queue_size']} packet_assignments={report['packet_assignment_count']} "
          f"near={report['near_match_count']} hard_neg={report['hard_negative_count']} "
          f"(disc={report['hard_negative_discovery_count']}·syn={report['hard_negative_synthetic_count']})")
    print(f"- buckets: {report['bucket_distribution']}")
    print(f"- source_roles: {report['source_role_distribution']}")
    print(f"- gates: reviewer_packet_exportable={report['reviewer_packet_exportable']} "
          f"labeler_prediction_hidden={report['labeler_prediction_hidden']} gold_ready={report['gold_ready']} "
          f"merge_allowed={report['merge_allowed']}")
    print(f"- acquisition next_fetch_plan: {linkage['next_fetch_plan']}")
    print(f"- agent_schema: near_match_queue_priority={agent_schema['near_match_queue_priority']} "
          f"reviewer_packet_priority={agent_schema['reviewer_packet_priority']} "
          f"embedding_llm_adjudicator={agent_schema['embedding_llm_adjudicator']['status']} "
          f"no_merge_without_gate={agent_schema['no_merge_without_gate']} llm_invoked={agent_schema['llm_invoked']}")
    print(f"- labeler_facing_view[0] keys (no bucket/prediction): "
          f"{sorted(queue['labeler_view'][0].keys()) if queue['labeler_view'] else 'empty'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
