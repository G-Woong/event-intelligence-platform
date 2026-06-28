"""ADR#79 — R1 discrete-event acquisition + deterministic recall probe (병합 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0).

ADR#77/#78 이 실측한 frontier: cross-source near-match 0(all below hard floor). 그 0 의 원인 (i) detector miss(같은
사건·recall 한계) vs (ii) broad-topic different-events 가 **단일 broad/7d run 으로는 미분리**. ADR#78 의
`_acquisition_strategy_next` 가 지목한 다음 레버 두 가지를 이 모듈이 더한다(재구현 0·ADR#76/#78 함수 재사용):

  - **discrete-event acquisition(Lane B)**: broad/7d 대신 **단일 이산 사건·1d·named entity** seed 로 좁혀 (ii)
    different-events 변수를 줄인다 → (i) 를 검증 가능하게 격리. seed shape 를 엄격 검증(broad umbrella 거부·tight
    window·event phrase 요구). 실 live 는 bounded·opt-in·승인 시만(이번 턴 user opt 'synthetic only' → live 미실행).
  - **deterministic recall probe(Lane C·핵심)**: `near_match_recall_probe` 로 reviewer-routing 후보 recall 을
    높인다(org/acronym alias·light stemming·feature attribution). **merge 경로 불변**(probe 는 cluster_records/
    fingerprint 미호출) — recall 완화는 reviewer 라우팅에만. synthetic known-paraphrase fixture 로 lever 를
    결정론 검증(below-floor 같은-사건 lift·different-events 미lift).

절대 불변(상속·상용 안전 계약):
  - **(i)/(ii) 단정 0**: recall probe 는 synthetic 에서 lever 가 작동함을 증명할 뿐, 실 frontier 의 같은/다른 사건을
    단정하지 않는다(reviewer 라벨 필요·indeterminate 보존). same_event 단정 0·gold 생성 0.
  - **recall probe = reviewer-routing only**: merge_allowed=False·recall_probe_applies_to_merge=False 불변.
  - **합성→production 둔갑 0 / live opt-in·secret-safe / no merge·LLM·embedding·DB·전송·secret read / public IU 0**.
  - **source role guard**: production candidate·anchor 는 publishable(official/article/news)만. community/market/
    catalog/search anchor 거부.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.near_match_recall_probe import (
    DEFAULT_ROUTING_FLOOR,
    NORMALIZATION_FEATURES,
    build_recall_probe_validation_fixture,
    summarize_recall_probe,
)
from backend.app.tools.r1_production_candidate_acquisition import (
    PCAND_BLOCKED_STATES,
    PROD_BATCH_ID,
)
from backend.app.tools.r1_targeted_live_acquisition import (
    REQUIRED_OPS_COPY,
    run_targeted_live_acquisition_and_near_match_diagnostic,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "r1_discrete_event_acquisition_and_recall_probe"

# ── discrete-event seed 검증 어휘(§5: 단일 이산 사건·1d·named entity·event phrase; broad umbrella 거부) ─────────
# event phrase 명사(이산 사건 신호) — entity 만 있는 broad anchor 와 구분.
_EVENT_NOUNS = frozenset({
    "ruling", "decision", "verdict", "judgment", "judgement", "announcement", "acquisition", "merger",
    "sanction", "sanctions", "result", "results", "launch", "strike", "attack", "ban", "approval",
    "indictment", "settlement", "resignation", "deal", "vote", "earnings", "recall", "lawsuit", "ipo",
    "bankruptcy", "ceasefire", "summit", "hearing", "statement", "cut", "hike", "raid", "explosion",
    "crash", "outage", "breach", "ousted", "resigns", "wins", "elected",
})
# broad umbrella(이산 사건 아님 — 지속 주제/기관 단독). 이들 단독이면 거부(event phrase 가 붙어야 discrete).
_BROAD_UMBRELLA_TOPICS = frozenset({
    "federal reserve", "ukraine war", "ukraine russia war", "russia ukraine war", "ai regulation",
    "artificial intelligence", "climate change", "stock market", "middle east", "trade war",
    "interest rates", "the economy", "politics", "election", "immigration", "inflation",
})
# community/market/catalog/search-only 의도(anchor 금지·ADR#78 정합).
_NON_ANCHOR_TERMS = ("reddit", "forum", "subreddit", "twitter", "stock price", "ticker",
                     "marketplace", "catalog", "product listing")

# discrete-event seeds(code-proposed **shape** — 특정 6월 사건 날조 0; 지속 기관의 이산 결정 형태·실 내용은 live 창 의존).
# seed_source 로 정직 표기(user_supplied 아님). 실 live 는 승인 시만(이번 턴 미실행).
DISCRETE_EVENT_SEEDS: list[dict] = [
    {"seed_id": "fomc_decision", "topic": "Federal Reserve FOMC rate decision", "topic_key": "fomc",
     "time_window": "1d", "event_type": "monetary_policy", "seed_source": "code_proposed_shape",
     "rationale": "단일 FOMC 결정일은 이산 사건·양 매체 동시 집중 보도·1d(ADR#78 broad 7d 대비 격리)"},
    {"seed_id": "scotus_opinion", "topic": "Supreme Court major ruling", "topic_key": "scotus",
     "time_window": "1d", "event_type": "judicial", "seed_source": "code_proposed_shape",
     "rationale": "이산 사법 판결·발표일 양 매체 cross-coverage·1d"},
    {"seed_id": "ecb_decision", "topic": "European Central Bank rate decision", "topic_key": "ecb",
     "time_window": "1d", "event_type": "monetary_policy", "seed_source": "code_proposed_shape",
     "rationale": "단일 ECB 결정일은 이산 사건·1d(KO 아님·영문 breadth)"},
]


def validate_discrete_event_seed(seed: dict) -> dict:
    """seed 가 §5 discrete-event 요건(단일 이산 사건·tight window·named entity+event phrase·anchor 친화)을 만족하는가.

    ADR#78 `validate_query_seed` 보다 **엄격**: broad umbrella 단독 거부·tight window(1d/2d)·event phrase 요구.
    검증 실패 사유 명시(조용히 통과 0). community/market/catalog-only 의도면 거부(anchor 금지)."""
    topic = (seed.get("topic") or "").strip()
    low = topic.lower()
    window = (seed.get("time_window") or "").strip()
    words = low.split()
    reasons: list[str] = []

    if any(t in low for t in _NON_ANCHOR_TERMS):
        reasons.append("community_market_catalog_only_topic")
    if window not in ("1d", "2d"):
        reasons.append("time_window_not_discrete")            # 이산 사건은 tight window(1d/2d)만.
    if len(words) < 2:
        reasons.append("topic_not_event_specific")            # 단일 generic 단어는 이산 사건 아님.
    has_event_phrase = any(w in _EVENT_NOUNS for w in words)
    has_date = any(w.isdigit() and len(w) == 4 for w in words)   # 연도 등 날짜 qualifier.
    if low in _BROAD_UMBRELLA_TOPICS:
        reasons.append("broad_umbrella_topic")                # 기관/주제 단독 — 이산 사건 아님.
    elif len(words) >= 2 and not (has_event_phrase or has_date):
        reasons.append("no_discrete_event_phrase")            # entity 만·사건 구 부재(broad lean).

    return {
        "seed_id": seed.get("seed_id"),
        "topic": topic,
        "time_window": window,
        "event_type": seed.get("event_type"),
        "seed_source": seed.get("seed_source") or "code_proposed_shape",
        "discrete_event_shape": bool(has_event_phrase or has_date) and not reasons,
        "valid": not reasons,
        "reject_reasons": reasons,
    }


def _recall_probe_section(routing_floor: float) -> dict:
    """deterministic recall probe 를 synthetic known-paraphrase fixture 로 실행(network 0·결정론·merge 미적용).

    below-floor 같은-사건 paraphrase 를 routing 으로 lift(recall 개선 측정)·different-events 미lift(판별) 증명.
    score 는 internal-only·body-free 요약(제목 전문 0). reviewer 라우팅 한정·merge 불변."""
    fixture = build_recall_probe_validation_fixture()
    summary = summarize_recall_probe(fixture, routing_floor=routing_floor)
    return summary


def refine_root_cause_with_recall_probe(gap: dict, probe_summary: dict) -> dict:
    """recall probe 결과로 (i)/(ii) 분리를 **구조적으로 진전**시키되 단정하지 않는다(ambiguity 보존).

    probe 가 synthetic 에서 lever 작동(below-floor 같은-사건 lift)을 증명 → (i) recall-miss 는 **실재하고 고칠 수
    있는 경로**임이 확인됨. 그러나 실 ADR#77/#78 below-floor 쌍이 (i)인지 (ii)인지는 **discrete-event 1d live
    candidate pair 에 probe 를 적용해야** 알 수 있다(이번 턴 user opt synthetic-only → 미실행). same_event 단정 0."""
    lifted = int(probe_summary.get("pairs_newly_routed_by_probe") or 0)
    entity_lifts = int(probe_summary.get("pairs_newly_routed_sharing_entity") or 0)
    return {
        "recall_probe_lever_demonstrated": lifted > 0,
        "known_paraphrase_pairs_lifted": lifted,
        "known_paraphrase_pairs_lifted_sharing_entity": entity_lifts,
        "live_frontier_verdict": "deferred_no_live_candidate_pairs_this_turn",
        "interpretation": (
            "recall probe lifts KNOWN below-floor same-event paraphrases into reviewer routing via "
            "organization/acronym alias + light stemming (the (i) recall-miss lever is real and works on known "
            "synthetic cases). whether the ACTUAL ADR#77/#78 live below-floor pairs are (i) detector-miss or (ii) "
            "different-events remains UNRESOLVED — separating them requires applying this probe to discrete-event "
            "1d LIVE candidate pairs (deferred this turn). no same-event asserted; merge path untouched"),
        "near_match_gap_status": gap.get("near_match_gap_status"),
        "root_cause_confidence": gap.get("root_cause_confidence"),
        "same_event_truth_asserted": False,
    }


def _discrete_acquisition_frontier(
    *, base_frontier: dict, seed_validations: list[dict], selected: Optional[dict],
    probe_summary: dict, refine: dict, provider_ready: bool, korean_ready: bool,
) -> dict:
    """§9 internal ops sanitized acquisition frontier(same_event truth·score·rationale·predicted·raw body·PII·secret 0).

    ADR#78 frontier 를 discrete-seed + recall-probe 표면으로 확장(read-only·public truth 아님)."""
    return {
        "contract": "InternalOpsDiscreteAcquisitionFrontier",
        "discrete_event_seed_selected": selected.get("seed_id") if selected else None,
        "discrete_event_seed_source": selected.get("seed_source") if selected else None,
        "discrete_event_time_window": selected.get("time_window") if selected else None,
        "discrete_seed_valid_count": sum(1 for v in seed_validations if v["valid"]),
        "near_match_gap_status": base_frontier.get("near_match_gap_status"),
        "root_cause_hypotheses": base_frontier.get("root_cause_hypotheses"),
        "root_cause_confidence": base_frontier.get("root_cause_confidence"),
        "max_recall_probe_score": probe_summary.get("max_recall_probe_score"),
        "recall_probe_pairs_newly_routed": probe_summary.get("pairs_newly_routed_by_probe"),
        "recall_probe_applies_to_merge": False,
        "recall_probe_lever_demonstrated": refine.get("recall_probe_lever_demonstrated"),
        "live_candidate_count": base_frontier.get("live_candidate_count"),
        "production_candidate_status": base_frontier.get("production_candidate_status"),
        "blocked_reason": base_frontier.get("blocked_reason"),
        "provider_breadth_next_action": "wire GDELT cooldown-honored + key-free RSS multi-outlet fleet for breadth"
                                        if provider_ready else "provider plan not ready",
        "korean_source_next_action": "wire naver_news_search adapter for KO topic-targeted overlap (KO floor lever)"
                                     if korean_ready else "korean plan not ready",
        "current_r1_gap": base_frontier.get("current_r1_gap"),
        "production_gold_count": base_frontier.get("production_gold_count"),
        "r2_r7_no_go": True,
        "required_copy": list(REQUIRED_OPS_COPY) + [
            "Recall probe is reviewer-routing only, not merge",
            "Recall probe lift on synthetic does not assert same-event on live frontier",
        ],
        "flags": {"no_public_truth": True, "no_same_event_truth": True, "no_score": True,
                  "no_rationale": True, "no_predicted_status": True, "no_raw_body": True, "no_secret": True},
    }


def run_discrete_event_acquisition_and_recall_probe(
    *, directory: Optional[Any] = None, batch_id: str = PROD_BATCH_ID, as_of: Optional[str] = None,
    live_query: bool = False, seeds: Optional[list[dict]] = None,
    recall_routing_floor: float = DEFAULT_ROUTING_FLOOR,
    transport_factory: Optional[Callable[[str, str], Optional[Callable[[str], Optional[str]]]]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None, host_gate: Any = None,
    readiness_fn: Optional[Callable[[], dict]] = None, gate_fn: Optional[Callable[..., dict]] = None,
    synthetic_batch_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """discrete-event acquisition + deterministic recall probe(병합 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0).

    1) discrete-event seed 엄격 검증(§5) → 2) ADR#78 gate/diagnostic/provider/Korean 재사용(dry/live) →
    3) deterministic recall probe(synthetic known-paraphrase·reviewer-routing only·merge 불변) →
    4) (i)/(ii) 분리 구조 진전(단정 0·indeterminate 보존) → 5) §4 output + sanitized frontier + 안전 플래그.
    어떤 경로도 입력 날조·merge·LLM·embedding·DB·전송·secret read·same_event 확정·label 생성·public IU 를 하지 않는다.

    test: transport_factory + env_probe_fn 주입 시 결정론(network 0·실 `.env` 미접촉). live_query=False(기본·이번 턴)."""
    use_seeds = list(seeds) if seeds is not None else list(DISCRETE_EVENT_SEEDS)
    seed_validations = [validate_discrete_event_seed(s) for s in use_seeds]
    valid_seeds_meta = [v for v in seed_validations if v["valid"]]
    # ADR#78 gate 에 넘길 valid seed(원본 dict — topic/topic_key/time_window/event_type 보존).
    valid_input_seeds = [s for s, v in zip(use_seeds, seed_validations, strict=True) if v["valid"]]
    selected = valid_seeds_meta[0] if valid_seeds_meta else None

    # ── ADR#78 targeted gate/diagnostic/provider/Korean 재사용(dry/live·둔갑 0) ──
    base = run_targeted_live_acquisition_and_near_match_diagnostic(
        directory=directory, batch_id=batch_id, as_of=as_of, live_query=live_query,
        seeds=valid_input_seeds or None,
        transport_factory=transport_factory, env_probe_fn=env_probe_fn, host_gate=host_gate,
        readiness_fn=readiness_fn, gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)

    # ── deterministic recall probe(Lane C·synthetic known-paraphrase·reviewer-routing only·merge 불변) ──
    probe_summary = _recall_probe_section(recall_routing_floor)
    refine = refine_root_cause_with_recall_probe(
        {"near_match_gap_status": base["near_match_gap_status"],
         "root_cause_confidence": base["root_cause_confidence"]}, probe_summary)

    production_candidate_status = base["production_candidate_status"]
    blocked = production_candidate_status in PCAND_BLOCKED_STATES
    blocked_reason = production_candidate_status if blocked else ""

    band = base.get("band_diagnostic") or {}
    max_title_jaccard = float(band.get("max_cross_source_title_jaccard") or 0.0)

    provider_ready = bool(base["provider_expansion_plan_ready"])
    korean_ready = bool(base["korean_source_strategy_ready"])

    discrete_frontier = _discrete_acquisition_frontier(
        base_frontier=base["internal_ops_acquisition_frontier"], seed_validations=seed_validations,
        selected=selected, probe_summary=probe_summary, refine=refine,
        provider_ready=provider_ready, korean_ready=korean_ready)

    # block_reasons: discrete seed 거부 + base 승계(중복 제거).
    block_reasons: list[str] = list(base.get("block_reasons") or [])
    invalid = [v for v in seed_validations if not v["valid"]]
    if invalid and not valid_seeds_meta:
        block_reasons = list(dict.fromkeys(["no_valid_discrete_event_seed", *block_reasons]))

    next_actions = list(dict.fromkeys([
        "apply recall probe to discrete-event 1d LIVE candidate pairs to empirically separate (i) detector-miss "
        "from (ii) different-events (deferred this turn — bounded live, user opt-in required)",
        *(base.get("next_actions") or []),
    ]))

    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        # actual input 재확인(ADR#72/#76/#78 gate passthrough).
        "actual_input_rechecked": base["actual_input_rechecked"],
        "actual_contact_evidence_found": base["actual_contact_evidence_found"],
        "actual_returned_labels_found": base["actual_returned_labels_found"],
        "actual_input_status": base["actual_input_status"],
        # discrete-event acquisition(§5).
        "discrete_event_seed_selected": selected.get("seed_id") if selected else None,
        "discrete_event_seed_source": selected.get("seed_source") if selected else None,
        "discrete_event_time_window": selected.get("time_window") if selected else None,
        "discrete_event_seeds": [
            {"seed_id": s["seed_id"], "topic": s["topic"], "time_window": s.get("time_window"),
             "event_type": s.get("event_type"), "seed_source": s.get("seed_source"),
             "seed_rationale": s.get("rationale")} for s in use_seeds],
        "discrete_event_seed_validations": seed_validations,
        # targeted live(opt-in·이번 턴 synthetic-only → 미실행).
        "targeted_live_query_approved": bool(live_query),
        "targeted_live_query_executed": base["targeted_live_query_executed"],
        "live_call_count": base["live_call_count"],
        "providers_used": base["providers_used"],
        "live_candidate_count": base["live_candidate_count"],
        "comparison_pair_count": base["live_candidate_count"],   # publishable cross-source 비교쌍(= same-event 매치 아님).
        "max_title_jaccard": round(max_title_jaccard, 4),
        # near-match gap 진단(§5·양가 보존·단정 0) — ADR#78 승계 + recall-probe 구조 진전.
        "near_match_gap_status": base["near_match_gap_status"],
        "root_cause_hypotheses": base["root_cause_hypotheses"],
        "root_cause_confidence": base["root_cause_confidence"],
        "recall_probe_root_cause_refinement": refine,
        "same_event_truth_asserted": False,
        # deterministic recall probe(Lane C·핵심).
        "max_recall_probe_score": probe_summary["max_recall_probe_score"],
        "recall_probe_summary": probe_summary,
        "deterministic_recall_probe_ready": True,
        "recall_probe_applies_to_reviewer_routing_only": True,
        "recall_probe_applies_to_merge": False,
        "normalization_features_tested": list(NORMALIZATION_FEATURES),
        # production candidate(ADR#76 gate 재사용·freeze-only-live-derived·둔갑 0).
        "production_candidate_status": production_candidate_status,
        "production_candidate_batch_ready": base["production_candidate_batch_ready"],
        "production_batch_id": base["production_batch_id"],
        "production_frozen_pair_count": base["production_frozen_pair_count"],
        "candidate_provenance": base["candidate_provenance"],
        "blocked_reason": blocked_reason,
        # acquisition strategy(Lane D).
        "provider_breadth_plan_ready": provider_ready,
        "provider_expansion_plan": base["provider_expansion_plan"],
        "korean_source_path_ready": korean_ready,
        "korean_source_strategy": base["korean_source_strategy"],
        # acquisition frontier(Lane E·sanitized·read-only).
        "acquisition_frontier_status_persisted": True,   # body-free status artifact 로 emit(read-only·DB row 아님).
        "acquisition_frontier_ui_ready": True,
        "internal_ops_discrete_acquisition_frontier": discrete_frontier,
        # product bridge contracts(Lane F·runtime 0).
        "llm_rag_kg_contract_guard_ready": bool(
            base["llm_evidence_packet_contract_ready"] and base["rag_ingestion_gate_ready"]
            and base["kg_edge_eligibility_contract_ready"]),
        "llm_evidence_packet_contract_ready": base["llm_evidence_packet_contract_ready"],
        "rag_ingestion_gate_ready": base["rag_ingestion_gate_ready"],
        "kg_edge_eligibility_contract_ready": base["kg_edge_eligibility_contract_ready"],
        "community_reaction_layer_contract_ready": base["community_reaction_layer_contract_ready"],
        "public_iu_gate_ready": base["public_iu_gate_ready"],
        "product_bridge_runtime_built": base["product_bridge_runtime_built"],
        # R1 gap(prod passthrough).
        "production_gold_count": base["production_gold_count"],
        "current_r1_gap": base["current_r1_gap"],
        "r1_status": base["r1_status"],
        "r2_r7_no_go": True,
        # 안전 경계(정직·constant + base 파생).
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "score_exposed": base["score_exposed"],
        "rationale_exposed": base["rationale_exposed"],
        "predicted_status_exposed": base["predicted_status_exposed"],
        "raw_pii_exposed": base["raw_pii_exposed"],
        "raw_source_body_exposed": False,
        "no_public_intelligence_unit": True,
        "merge_allowed": base["merge_allowed"],
        "db_write": base["db_write"],
        "llm_invoked": base["llm_invoked"],
        "embedding_invoked": base["embedding_invoked"],
        "actual_sending_performed": False,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·드리프트 fail-loud).
    _assert_pii_safe(result, _path="r1_discrete_event_acquisition_output")
    return result


# ── CLI(기본 시도 0·network 0·DB 0·전송 0·secret read 0; --live-query 로 opt-in bounded discrete acquisition) ──
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="R1 discrete-event acquisition + deterministic recall probe "
                    "(ADR#79·병합 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0).")
    parser.add_argument("--batch-id", default=PROD_BATCH_ID, help="production-candidate freeze batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument(
        "--live-query", action="store_true",
        help="명시적 opt-in: 양 provider credential present 일 때만 bounded discrete-event live fetch(network·CI 아님·값 미노출).")
    parser.add_argument("--routing-floor", type=float, default=DEFAULT_ROUTING_FLOOR,
                        help="recall probe reviewer-routing floor(기본 0.2·merge threshold 아님).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    host_gate = None
    if ns.live_query:
        try:
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None

    out = run_discrete_event_acquisition_and_recall_probe(
        directory=ns.input_dir, batch_id=ns.batch_id, as_of=ns.as_of,
        live_query=ns.live_query, recall_routing_floor=ns.routing_floor, host_gate=host_gate)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: status={out['actual_input_status']} returned_labels={out['actual_returned_labels_found']}")
    print(f"- discrete_seed: selected={out['discrete_event_seed_selected']} source={out['discrete_event_seed_source']} "
          f"window={out['discrete_event_time_window']}")
    for v in out["discrete_event_seed_validations"]:
        print(f"  · {v['seed_id']}: valid={v['valid']} discrete_shape={v['discrete_event_shape']} reject={v['reject_reasons']}")
    print(f"- targeted_live: approved={out['targeted_live_query_approved']} executed={out['targeted_live_query_executed']} "
          f"live_calls={out['live_call_count']} comparison_pairs={out['comparison_pair_count']} max_jac={out['max_title_jaccard']}")
    print(f"- near_match_gap: status={out['near_match_gap_status']} confidence={out['root_cause_confidence']}")
    print(f"- recall_probe: max_score={out['max_recall_probe_score']} "
          f"newly_routed={out['recall_probe_summary']['pairs_newly_routed_by_probe']} "
          f"(sharing_entity={out['recall_probe_summary']['pairs_newly_routed_sharing_entity']}) "
          f"applies_to_merge={out['recall_probe_applies_to_merge']}")
    print(f"  · refinement: lever_demonstrated={out['recall_probe_root_cause_refinement']['recall_probe_lever_demonstrated']} "
          f"live_verdict={out['recall_probe_root_cause_refinement']['live_frontier_verdict']}")
    print(f"- production_candidate: status={out['production_candidate_status']} provenance={out['candidate_provenance']} "
          f"frozen={out['production_frozen_pair_count']}")
    print(f"- plans: provider_breadth_ready={out['provider_breadth_plan_ready']} korean_ready={out['korean_source_path_ready']}")
    print(f"- contracts: guard_ready={out['llm_rag_kg_contract_guard_ready']} runtime_built={out['product_bridge_runtime_built']}")
    print(f"- r1_gap: production={out['production_gold_count']} gap={out['current_r1_gap']} r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- gates: merge={out['merge_allowed']} llm={out['llm_invoked']} embedding={out['embedding_invoked']} "
          f"db_write={out['db_write']} sending={out['actual_sending_performed']}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
