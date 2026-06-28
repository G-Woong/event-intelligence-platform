"""ADR#81 — provider breadth + named single-event seed + KO source path orchestrator
(merge 0 · LLM 0 · embedding 0 · DB 0 · 전송 0 · secret read 0 · public IU 0).

ADR#80 실측: live recall lift 0(synthetic 미일반화). 분석 §2: 그 음성의 원인은 *프로젝트 사망*이 아니라 (a)
category-lean seed("Supreme Court ruling") + (b) 얇은 provider(Guardian×NYT) + (c) KO 경로 미연결. 이 모듈은 그
세 레버를 **실 acquisition frontier 로** 끌어내린다 — provider breadth inventory + named single-event seed bank +
KO source path 를 ADR#80 discrete base 와 합성해 §4 output 과 sanitized internal ops frontier 를 산출한다.

이번 턴 정책(§3·§7):
  - A(actual input 재확인)+B(provider breadth)+C(named seed)+E(KO path)+F(frontier)+G(community contract·docs) 채택.
  - D(bounded live): 이번 /compact 에 *이번 턴 live 실행 명시 승인 없음* → 기본 live_query=False →
    live_query_executed=False · status=blocked_no_live_opt_in · next_action=ask_for_bounded_live_run_approval(§7).
  - H(LLM/RAG/KG runtime)+I(public IU runtime): 금지.

절대 불변(상속·재확인):
  - merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret 값 0 · public IU 0 · same_event 단정 0 · production gold 0.
  - source role guard: community/market/catalog/search 는 anchor 불가(breadth inventory 가 강제).
  - breadth=acquisition support not truth · named seed=candidate generation not same-event proof · community=reaction only.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.ko_source_readiness import build_ko_source_readiness
from backend.app.tools.named_event_seed_bank import build_named_event_seed_bank
from backend.app.tools.provider_breadth_inventory import build_provider_breadth_inventory
from backend.app.tools.r1_discrete_event_acquisition import (
    run_discrete_event_acquisition_and_recall_probe,
)
from backend.app.tools.r1_production_candidate_acquisition import PROD_BATCH_ID
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

ACQ_OPERATION_NAME = "provider_breadth_named_seed_ko_path"

# §7 live 미승인 시 status(execution block·data 판정 아님).
LIVE_BLOCKED_NO_OPT_IN = "blocked_no_live_opt_in"

# §10 필수 정직 copy.
ACQUISITION_REQUIRED_COPY: tuple[str, ...] = (
    "Provider breadth is acquisition support, not truth",
    "Named seed is candidate generation, not same-event proof",
    "Community reaction is not an event anchor",
    "Production gold remains 0 until human labels are returned",
    "R2~R7 remain No-Go",
)


def build_provider_breadth_frontier(
    *, breadth: dict, seed_bank: dict, ko: dict, base: dict,
    live_executed: bool,
) -> dict:
    """§10 internal ops provider breadth frontier(sanitized·read-only·public truth 아님).

    same_event truth·per-pair score·rationale·predicted_status·raw body·PII·secret 미노출(스키마에 필드 부재 +
    _assert_pii_safe 재귀 가드). aggregate/status/count/next_action 만."""
    selected_seed = seed_bank.get("selected_seed_id")
    seed_type = "named_single_event" if selected_seed else (
        "none_named_seed_pending_operator_specification")
    next_action = (
        f"confirm_actual_event_for_named_seed:{selected_seed} then request bounded live run (host/rate honored)"
        if (not live_executed and selected_seed)
        else "review_live_recall_classification" if live_executed
        else "specify_named_entity_for_a_seed (operator)")
    return {
        "contract": "InternalOpsProviderBreadthFrontier",
        # provider breadth(§10).
        "provider_breadth_status": (
            f"ready_{breadth['anchor_eligible_count']}_anchor_of_{breadth['total_sources']}"
            if breadth.get("provider_breadth_inventory_ready") else "not_ready"),
        "provider_breadth_inventory_ready": bool(breadth.get("provider_breadth_inventory_ready")),
        "query_capable_provider_count": int(breadth.get("query_capable_publishable_count") or 0),
        "feed_only_provider_count": int(breadth.get("feed_only_publishable_count") or 0),
        "official_source_count": int(breadth.get("official_source_count") or 0),
        "search_url_candidate_count": int(breadth.get("search_url_candidate_count") or 0),
        "ko_official_news_count": int(breadth.get("ko_official_news_count") or 0),
        "community_reaction_only_count": int(breadth.get("community_reaction_only_count") or 0),
        "market_signal_only_count": int(breadth.get("market_signal_only_count") or 0),
        "catalog_enrichment_only_count": int(breadth.get("catalog_enrichment_only_count") or 0),
        "unknown_quarantine_count": int(breadth.get("unknown_quarantine_count") or 0),
        "anchor_eligible_count": int(breadth.get("anchor_eligible_count") or 0),
        # named seed(§10).
        "named_seed_bank_status": (
            f"ready_{seed_bank['named_seed_count']}_named_seeds"
            if seed_bank.get("named_single_event_seed_bank_ready") else "not_ready"),
        "named_seed_count": int(seed_bank.get("named_seed_count") or 0),
        "selected_seed_for_next_live_run": selected_seed,
        "seed_type": seed_type,
        # KO(§10).
        "ko_source_path_status": (
            f"ready_{ko['ko_official_news_count']}_ko_news_live"
            if ko.get("ko_source_path_ready") else "not_ready"),
        "ko_tokenization_risk_recorded": bool(ko.get("ko_tokenization_risk_recorded")),
        # live recall(shared·aggregate only·per-pair score 미노출).
        "latest_live_seed": base.get("discrete_event_seed_selected"),
        "live_recall_lift_status": base.get("live_recall_lift_status"),
        "max_live_recall_probe_score": round(float(base.get("max_live_recall_probe_score") or 0.0), 4),
        "newly_routed_count": int(base.get("live_pairs_newly_routed_by_probe") or 0),
        # production/gap(shared).
        "production_candidate_status": base.get("production_candidate_status"),
        "blocked_reason": base.get("blocked_reason") or "",
        "current_r1_gap": int(base.get("current_r1_gap") or 0),
        "r2_r7_no_go": True,
        # next action + copy.
        "acquisition_next_action": next_action,
        "required_copy": list(ACQUISITION_REQUIRED_COPY),
        "flags": {"no_public_truth": True, "no_same_event_truth": True, "no_score": True,
                  "no_rationale": True, "no_predicted_status": True, "no_raw_body": True,
                  "no_secret": True},
    }


def run_provider_breadth_named_seed_ko_path(
    *, directory: Optional[Any] = None, batch_id: str = PROD_BATCH_ID, as_of: Optional[str] = None,
    live_query: bool = False,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    probe_fn: Optional[Callable[[str], dict]] = None,
    base_result: Optional[dict] = None,
    transport_factory: Optional[Callable[[str, str], Optional[Callable[[str], Optional[str]]]]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None, host_gate: Any = None,
    readiness_fn: Optional[Callable[[], dict]] = None, gate_fn: Optional[Callable[..., dict]] = None,
    synthetic_batch_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """ADR#81 단일 진입 — discrete base(ADR#80) + provider breadth + named seed + KO path 합성 → §4 output + frontier.

    기본 live_query=False(이번 턴 승인 없음) → live 미실행·blocked_no_live_opt_in. base_result 주입 시 base 재실행
    생략(orchestrator 단위 테스트용). merge 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0·same_event 0·gold 0."""
    base = base_result if base_result is not None else run_discrete_event_acquisition_and_recall_probe(
        directory=directory, batch_id=batch_id, as_of=as_of, live_query=live_query,
        transport_factory=transport_factory, env_probe_fn=env_probe_fn, host_gate=host_gate,
        readiness_fn=readiness_fn, gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)

    breadth = build_provider_breadth_inventory(env_status_fn=env_status_fn)
    seed_bank = build_named_event_seed_bank()
    ko = build_ko_source_readiness(probe_fn=probe_fn)

    live_executed = bool(base.get("targeted_live_query_executed"))
    live_run_status = (base.get("live_recall_lift_status") if live_executed
                       else LIVE_BLOCKED_NO_OPT_IN)

    frontier = build_provider_breadth_frontier(
        breadth=breadth, seed_bank=seed_bank, ko=ko, base=base, live_executed=live_executed)

    block_reasons = list(dict.fromkeys([
        *( [LIVE_BLOCKED_NO_OPT_IN] if not live_executed else [] ),
        *(base.get("block_reasons") or []),
    ]))
    next_actions = list(dict.fromkeys([
        *( ["ask_for_bounded_live_run_approval (named seed queued · host/rate honored · 1~2 seeds max)"]
           if not live_executed else [] ),
        "wire key-free anchor-eligible breadth (gdelt cooldown-honored, federal_register, RSS fleet) into comparison pool",
        "wire key-free LIVE KO news (yna/hankyung/maekyung) into comparison pool for KO floor",
        *(base.get("next_actions") or []),
    ]))

    result = {
        "operation_name": ACQ_OPERATION_NAME,
        "batch_id": batch_id,
        # actual input 재확인(§3-A·base passthrough).
        "actual_input_rechecked": base.get("actual_input_rechecked"),
        "actual_contact_evidence_found": base.get("actual_contact_evidence_found"),
        "actual_returned_labels_found": base.get("actual_returned_labels_found"),
        "actual_input_status": base.get("actual_input_status"),
        # provider breadth(§3-B·§5).
        "provider_breadth_inventory_ready": breadth["provider_breadth_inventory_ready"],
        "query_capable_publishable_count": breadth["query_capable_publishable_count"],
        "feed_only_publishable_count": breadth["feed_only_publishable_count"],
        "official_source_count": breadth["official_source_count"],
        "search_url_candidate_count": breadth["search_url_candidate_count"],
        "ko_official_news_count": breadth["ko_official_news_count"],
        "community_reaction_only_count": breadth["community_reaction_only_count"],
        "market_signal_only_count": breadth["market_signal_only_count"],
        "catalog_enrichment_only_count": breadth["catalog_enrichment_only_count"],
        "unknown_quarantine_count": breadth["unknown_quarantine_count"],
        "anchor_eligible_count": breadth["anchor_eligible_count"],
        "provider_breadth_next_actions": breadth["provider_breadth_next_actions"],
        "provider_breadth_inventory": breadth["inventory"],
        "source_role_guard_preserved": bool(
            breadth["source_role_guard_preserved"] and ko["source_role_guard_preserved"]),
        # named single-event seed(§3-C·§6).
        "named_single_event_seed_bank_ready": seed_bank["named_single_event_seed_bank_ready"],
        "named_seed_count": seed_bank["named_seed_count"],
        "broad_seed_rejected_count": seed_bank["broad_seed_rejected_count"],
        "selected_seed_for_next_live_run": seed_bank["selected_seed_for_next_live_run"],
        "named_event_seed_bank": seed_bank["seed_bank"],
        # bounded live(§3-D·§7 — 이번 턴 승인 없음 → blocked_no_live_opt_in).
        "live_query_approved": bool(live_query),
        "live_query_executed": live_executed,
        "live_run_status": live_run_status,
        "live_call_count": base.get("live_call_count"),
        "providers_used": base.get("providers_used"),
        "comparison_pair_count": base.get("comparison_pair_count"),
        "max_live_recall_probe_score": base.get("max_live_recall_probe_score"),
        "live_pairs_newly_routed_by_probe": base.get("live_pairs_newly_routed_by_probe"),
        "live_recall_lift_status": base.get("live_recall_lift_status"),
        # production candidate(§3-D·base passthrough·freeze-only-live-derived·둔갑 0).
        "production_candidate_status": base.get("production_candidate_status"),
        "production_candidate_batch_ready": base.get("production_candidate_batch_ready"),
        "production_frozen_pair_count": base.get("production_frozen_pair_count"),
        "candidate_provenance": base.get("candidate_provenance"),
        # KO source path(§3-E·§8).
        "ko_source_path_ready": ko["ko_source_path_ready"],
        "ko_adapter_status": ko["ko_adapter_status"],
        "naver_adapter_status": ko["naver_adapter_status"],
        "newsapi_status": ko["newsapi_status"],
        "ko_tokenization_risk_recorded": ko["ko_tokenization_risk_recorded"],
        "ko_tokenization_risk": ko["ko_tokenization_risk"],
        "ko_floor_plan": ko["ko_floor_plan"],
        "ko_floor_solved": ko["ko_floor_solved"],
        # acquisition frontier(§3-F·§10·sanitized).
        "acquisition_frontier_ui_ready": True,
        "internal_ops_provider_breadth_frontier": frontier,
        # community reaction contract(§3-G·docs·runtime 0).
        "community_reaction_contract_updated": bool(base.get("community_reaction_layer_contract_ready")),
        # R1 gap(base passthrough).
        "production_gold_count": base.get("production_gold_count"),
        "current_r1_gap": base.get("current_r1_gap"),
        "r2_r7_no_go": True,
        # 안전 경계(정직·constant + base 파생).
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "score_exposed": bool(base.get("score_exposed")),
        "rationale_exposed": bool(base.get("rationale_exposed")),
        "predicted_status_exposed": bool(base.get("predicted_status_exposed")),
        "raw_pii_exposed": bool(base.get("raw_pii_exposed")),
        "raw_source_body_exposed": False,
        "no_public_intelligence_unit": True,
        "merge_allowed": bool(base.get("merge_allowed")),
        "db_write": bool(base.get("db_write")),
        "llm_invoked": bool(base.get("llm_invoked")),
        "embedding_invoked": bool(base.get("embedding_invoked")),
        "actual_sending_performed": False,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·드리프트 fail-loud).
    _assert_pii_safe(result, _path="r1_provider_breadth_acquisition_output")
    return result


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#81 provider breadth + named single-event seed + KO source path "
                     "(merge 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0; 기본 live 미실행)."))
    parser.add_argument("--batch-id", default=PROD_BATCH_ID, help="production-candidate freeze batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument("--live-query", action="store_true",
                        help="명시적 opt-in: bounded named-seed live fetch(network·CI 아님·값 미노출·승인 시만).")
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

    out = run_provider_breadth_named_seed_ko_path(
        directory=ns.input_dir, batch_id=ns.batch_id, as_of=ns.as_of,
        live_query=ns.live_query, host_gate=host_gate)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: status={out['actual_input_status']} returned_labels={out['actual_returned_labels_found']}")
    print(f"- provider_breadth: ready={out['provider_breadth_inventory_ready']} "
          f"query_capable={out['query_capable_publishable_count']} feed_only={out['feed_only_publishable_count']} "
          f"official={out['official_source_count']} search_url={out['search_url_candidate_count']} "
          f"ko_news={out['ko_official_news_count']}")
    print(f"    community={out['community_reaction_only_count']} market={out['market_signal_only_count']} "
          f"catalog={out['catalog_enrichment_only_count']} quarantine={out['unknown_quarantine_count']} "
          f"guard_preserved={out['source_role_guard_preserved']}")
    print(f"- named_seed_bank: ready={out['named_single_event_seed_bank_ready']} named={out['named_seed_count']} "
          f"broad_rejected={out['broad_seed_rejected_count']} selected={out['selected_seed_for_next_live_run']['seed_id'] if out['selected_seed_for_next_live_run'] else None}")
    print(f"- live: approved={out['live_query_approved']} executed={out['live_query_executed']} "
          f"status={out['live_run_status']} comparison_pairs={out['comparison_pair_count']} "
          f"max_live_score={out['max_live_recall_probe_score']} newly_routed={out['live_pairs_newly_routed_by_probe']}")
    print(f"- ko_path: ready={out['ko_source_path_ready']} tokenization_risk_recorded={out['ko_tokenization_risk_recorded']} "
          f"floor_solved={out['ko_floor_solved']}")
    print(f"- production_candidate: status={out['production_candidate_status']} provenance={out['candidate_provenance']} "
          f"frozen={out['production_frozen_pair_count']}")
    print(f"- r1_gap: production={out['production_gold_count']} gap={out['current_r1_gap']} r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- gates: merge={out['merge_allowed']} llm={out['llm_invoked']} embedding={out['embedding_invoked']} "
          f"db_write={out['db_write']} sending={out['actual_sending_performed']} public_iu={not out['no_public_intelligence_unit']}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
