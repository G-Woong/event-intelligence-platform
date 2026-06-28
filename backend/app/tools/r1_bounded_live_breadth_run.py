"""ADR#82 — bounded live breadth run + named-event date-pin gate + production-candidate freeze attempt
(merge 0 · LLM 0 · embedding 0 · DB 0 · 전송 0 · secret read 0 · public IU 0).

ADR#81 은 provider breadth inventory + named single-event seed bank + KO source path 를 *acquisition frontier 로*
끌어내렸으나 실 live 는 미실행(blocked_no_live_opt_in). 분석 §2(ADR#82): provider breadth 의 anchor_eligible(25)는
*capability 분류*일 뿐, 실제 cross-source live 경로(cross_source_live_overlap_smoke→run_provider_query)에 wired 된
어댑터는 {guardian,nyt} 2개뿐이고, named seed 는 *실제 발생 날짜로 핀* 되어야 discrete event 가 된다. 이 모듈은:
  - named seed 에 **date-pin 게이트**를 건다(§5): occurrence_date(ISO) 없으면 missing_date_pinned_named_event.
  - provider breadth inventory → **실제 bounded live pool** 을 정직히 산출한다(§6): anchor_eligible ∩ adapter_wired
    ∩ credential = live_runnable_now, query-capable 이나 미wired(gdelt/sec_edgar/federal_register)는 wire-first.
  - live-derived pair 가 생기면 **production candidate freeze 를 시도**한다(§7·base passthrough). 없으면 blocked 정직.
  - KO source lane 을 EN run 과 분리해 구체화한다(§8).
  - sanitized internal ops frontier 를 산출한다(§9).

이번 턴 정책(§3·§7): A(actual input 재확인)+C(breadth→pool wiring)+D 조건부(live pair 없음→freeze 없음)+E(KO lane)
+F 제한(snapshot 설계만·미작성)+G(community contract). **B(bounded live)=이번 /compact 에 구체적 date-pin·실행 승인
미제공 → live_query=False & date_pinned=False → live_query_executed=False · blocked_reason=
missing_date_pinned_named_event · next_action=provide_or_select_date_pinned_event(§5).** H/I(LLM/RAG/KG/public IU
runtime): 금지.

절대 불변: merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret 값 0 · public IU 0 · same_event 단정 0 · production
gold 0. provider breadth=acquisition support not truth · named seed=candidate generation not same-event proof ·
date-pin=operator gate not occurrence proof · freeze=reviewer worklist not truth · community=reaction only.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.ko_source_readiness import build_ko_source_lane
from backend.app.tools.named_event_seed_bank import validate_date_pinned_named_event
from backend.app.tools.r1_production_candidate_acquisition import PROD_BATCH_ID
from backend.app.tools.r1_provider_breadth_acquisition import (
    run_provider_breadth_named_seed_ko_path,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

BOUNDED_OPERATION_NAME = "bounded_live_breadth_run_and_candidate_freeze_attempt"

# §5 date-pin 미충족 시 binding blocker(execution block — data 판정 아님).
BLOCKED_MISSING_DATE_PIN = "missing_date_pinned_named_event"
# §7 live 미승인 시 status.
LIVE_BLOCKED_NO_OPT_IN = "blocked_no_live_opt_in"
# date-pin 승인되어도 *그 특정 dated event* 를 실제 쿼리에 꽂는 plumbing 미구현 시 blocker(정직·fail-closed).
BLOCKED_QUERY_WIRING = "date_pinned_query_wiring_not_implemented"

# 정직 capability flag: date-pin 은 operator 게이트일 뿐, base 는 curated seed 를 topic+상대윈도우로 쿼리한다 →
# operator 가 pin 한 event X 의 *정확한 dated 쿼리* 를 base 에 꽂는 배선은 아직 없다(pinned event 승인 ≠ 쿼리 대상).
# 그 decoupling 을 숨기지 않고 fail-closed: 이 flag 가 False 인 동안 bounded live 는 실행 불가(별도 ADR 에서 배선).
LIVE_QUERY_TARGET_WIRED = False

# §10 필수 정직 copy(bounded live + freeze 경계 명시).
BOUNDED_LIVE_REQUIRED_COPY: tuple[str, ...] = (
    "Provider breadth is acquisition support, not truth",
    "Named seed is candidate generation, not same-event proof",
    "A bounded live run requires an operator-confirmed date-pinned event",
    "Community reaction is not an event anchor",
    "Production candidate freeze is a reviewer worklist, not same-event truth",
    "Production gold remains 0 until human labels are returned",
    "R2~R7 remain No-Go",
)


def _adapter_wired_providers() -> frozenset[str]:
    """cross_source_live_overlap_smoke 의 run_provider_query 에 실제 wired 된 어댑터 집합(이 경로의 live 실행가능)."""
    try:
        from backend.app.tools.provider_query_adapters import ADAPTER_WIRED_PROVIDERS
        return frozenset(ADAPTER_WIRED_PROVIDERS)
    except Exception:
        return frozenset()   # fail-closed: 어댑터 모듈 미가용이면 wired 0(guardian/nyt overclaim 금지).


def build_bounded_live_provider_pool(inventory_rows: list[dict]) -> dict:
    """§6 — provider breadth inventory → *실제 bounded live pool* (정직 교집합·실행가능≠breadth 크기).

    분석 §2-Q1/Q2: anchor_eligible(25)는 capability 분류일 뿐. 실제 cross-source live 경로에 wired 된 어댑터는
    {guardian,nyt} 2개뿐. live_runnable_now = anchor_eligible ∩ adapter_wired ∩ credential_present. query-capable
    이나 미wired(gdelt/sec_edgar/federal_register)는 wire-first(이번 턴 실행 불가). feed_only KO 뉴스는 KO lane.
    source role guard 약화 0(community/market/catalog/search 는 애초에 anchor_eligible=False 라 pool 진입 불가)."""
    wired = _adapter_wired_providers()
    pool_rows: list[dict] = []
    for r in inventory_rows or []:
        if not r.get("anchor_eligible"):
            continue
        sid = r.get("source_id")
        cred_required = bool(r.get("credential_required"))
        cred_map = r.get("credential_presence_secret_safe") or {}
        credential_present = (not cred_required) or (
            bool(cred_map) and all(v == "present" for v in cred_map.values()))
        qc = str(r.get("query_capability") or "")
        query_capable = bool(qc) and qc != "feed_only"
        adapter_wired = sid in wired
        live_runnable_now = adapter_wired and credential_present
        if live_runnable_now:
            next_action = "live_runnable — bounded run(approval+date-pin+rate 시)"
        elif adapter_wired and not credential_present:
            next_action = "set_env (credential missing) → live_runnable"
        elif query_capable:
            next_action = "wire_run_provider_query_adapter_first (query-capable·미wired·이번 턴 불가)"
        else:
            next_action = "feed_only_or_ko_lane (topic query 아님 — breadth/KO lane)"
        pool_rows.append({
            "source_id": sid,
            "category": r.get("category"),
            "adapter_wired_for_cross_source_query": adapter_wired,
            "key_free": not cred_required,
            "credential_present": credential_present,
            "query_capable": query_capable,
            "live_runnable_now": live_runnable_now,
            "query_capability": qc,
            "next_action": next_action,
        })
    runnable = [p for p in pool_rows if p["live_runnable_now"]]
    key_free_runnable = [p for p in runnable if p["key_free"]]
    cred_runnable = [p for p in runnable if not p["key_free"]]
    query_capable_not_wired = sorted(
        p["source_id"] for p in pool_rows
        if p["query_capable"] and not p["adapter_wired_for_cross_source_query"])
    return {
        "bounded_live_provider_pool": pool_rows,
        "providers_in_pool": sorted(p["source_id"] for p in runnable),
        "provider_breadth_used": len(runnable),
        "key_free_provider_count": len(key_free_runnable),
        "credential_required_provider_count": len(cred_runnable),
        "query_capable_not_yet_wired": query_capable_not_wired,
        "adapter_wired_providers": sorted(wired),
        "source_role_guard_preserved": all(
            p["category"] in (
                "query_capable_publishable", "feed_only_publishable", "official_source",
                "ko_official_news")
            for p in pool_rows),
    }


def build_bounded_live_breadth_frontier(*, out: dict) -> dict:
    """§9 internal ops bounded live breadth frontier(sanitized·read-only·public truth 아님).

    same_event truth·per-pair score·rationale·predicted_status·raw body·PII·secret 미노출(스키마에 필드 부재 +
    _assert_pii_safe 재귀 가드). aggregate/status/count/next_action 만."""
    return {
        "contract": "InternalOpsBoundedLiveBreadthFrontier",
        "latest_bounded_live_run_status": out["live_run_status"],
        "named_seed_selected": out["named_seed_selected"],
        "named_seed_date_pin_status": out["named_seed_date_pin_status"],
        "selected_seed_actual_occurrence": out["selected_seed_actual_occurrence"],
        "live_query_approved": bool(out["live_query_approved"]),
        "live_query_executed": bool(out["live_query_executed"]),
        "live_call_count": int(out["live_call_count"] or 0),
        "providers_used": list(out["providers_used"] or []),
        "provider_breadth_used": int(out["provider_breadth_used"] or 0),
        "key_free_provider_count": int(out["key_free_provider_count"] or 0),
        "credential_required_provider_count": int(out["credential_required_provider_count"] or 0),
        "comparison_pair_count": int(out["comparison_pair_count"] or 0),
        "max_recall_probe_score": round(float(out["max_recall_probe_score"] or 0.0), 4),
        "newly_routed_count": int(out["live_pairs_newly_routed_by_probe"] or 0),
        "production_candidate_status": out["production_candidate_status"] or "blocked",
        "production_candidate_batch_ready": bool(out["production_candidate_batch_ready"]),
        "production_frozen_pair_count": int(out["production_frozen_pair_count"] or 0),
        "sanitized_snapshot_status": out["sanitized_snapshot_status"],
        "ko_source_lane_status": out["ko_source_lane_status"],
        "ko_named_seed_needed": bool(out["ko_named_seed_needed"]),
        "ko_floor_current": int(out["ko_floor_current"] or 0),
        "ko_floor_required": int(out["ko_floor_required"] or 0),
        "blocked_reason": out["blocked_reason"] or "",
        "acquisition_next_action": out["acquisition_next_action"],
        "current_r1_gap": int(out["current_r1_gap"] or 0),
        "production_gold_count": int(out["production_gold_count"] or 0),
        "r2_r7_no_go": True,
        "required_copy": list(BOUNDED_LIVE_REQUIRED_COPY),
        "flags": {"no_public_truth": True, "no_same_event_truth": True, "no_score": True,
                  "no_rationale": True, "no_predicted_status": True, "no_raw_body": True,
                  "no_secret": True},
    }


def run_bounded_live_breadth_run(
    *, directory: Optional[Any] = None, batch_id: str = PROD_BATCH_ID, as_of: Optional[str] = None,
    live_query: bool = False, pinned_event: Optional[dict] = None,
    base_result: Optional[dict] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    probe_fn: Optional[Callable[[str], dict]] = None,
    transport_factory: Optional[Callable[[str, str], Optional[Callable[[str], Optional[str]]]]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None, host_gate: Any = None,
    readiness_fn: Optional[Callable[[], dict]] = None, gate_fn: Optional[Callable[..., dict]] = None,
    synthetic_batch_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """ADR#82 단일 진입 — ADR#81 base + date-pin gate + bounded live pool + freeze attempt + KO lane → §4 + frontier.

    live_eligible = live_query ∧ date_pinned. 둘 중 하나라도 미충족이면 base 를 live_query=False 로 호출(네트워크 0)
    하고 blocked 정직 산출. 이번 턴 기본 live_query=False·pinned_event=None → date_pinned=False → blocked_reason=
    missing_date_pinned_named_event. base_result 주입 시 base 재실행 생략(orchestrator 단위 테스트용).
    merge 0 · LLM 0 · embedding 0 · DB 0 · 전송 0 · secret read 0 · same_event 0 · gold 0."""
    # ── ① ADR#81 base(breadth/seed/KO/actual-input/live passthrough). date-pin 미충족이면 live 강제 차단 ──
    # base 를 먼저 (live 미실행으로) 호출해 selected seed 를 얻고, date-pin 판정 후 eligible 일 때만 live 재호출.
    base = base_result if base_result is not None else run_provider_breadth_named_seed_ko_path(
        directory=directory, batch_id=batch_id, as_of=as_of, live_query=False,
        env_status_fn=env_status_fn, probe_fn=probe_fn, transport_factory=transport_factory,
        env_probe_fn=env_probe_fn, host_gate=host_gate, readiness_fn=readiness_fn,
        gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)

    sel = base.get("selected_seed_for_next_live_run")
    named_seed_selected = sel.get("seed_id") if isinstance(sel, dict) else sel

    # ── ② date-pin 게이트(§5) — operator pinned_event 우선, 없으면 selected seed(occurrence_date 부재 → not pinned) ──
    pin_target = pinned_event if pinned_event is not None else (sel if isinstance(sel, dict) else {})
    date_pin = validate_date_pinned_named_event(pin_target or {})
    date_pinned = bool(date_pin["date_pinned"])
    selected_seed_actual_occurrence = date_pin["occurrence_date"]
    named_seed_date_pin_status = (
        f"pinned:{selected_seed_actual_occurrence}" if date_pinned
        else f"not_pinned:{','.join(date_pin['rejection_reasons']) or 'unknown'}")

    # ── ③ bounded live pool(§6) — breadth inventory → 실제 실행가능 교집합(정직) ──
    pool = build_bounded_live_provider_pool(base.get("provider_breadth_inventory") or [])

    # ── ④ live eligibility(§3-B·§5·§7) — live_query ∧ date_pinned ∧ 실 query-wiring. 셋 충족 시 base live 재호출 ──
    # date-pin 은 operator 게이트일 뿐 — 그 *특정 dated event* 를 실제 쿼리에 꽂는 plumbing 미구현(LIVE_QUERY_TARGET_WIRED
    # =False) → fail-closed(pinned event 승인 ≠ 쿼리 대상 둔갑 금지). 배선되면 그때만 base 를 live 로 재호출.
    live_eligible = bool(live_query) and date_pinned and LIVE_QUERY_TARGET_WIRED
    if live_eligible and base_result is None:
        base = run_provider_breadth_named_seed_ko_path(
            directory=directory, batch_id=batch_id, as_of=as_of, live_query=True,
            env_status_fn=env_status_fn, probe_fn=probe_fn, transport_factory=transport_factory,
            env_probe_fn=env_probe_fn, host_gate=host_gate, readiness_fn=readiness_fn,
            gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)
    live_executed = bool(base.get("live_query_executed"))
    live_run_status = (base.get("live_recall_lift_status") if live_executed else LIVE_BLOCKED_NO_OPT_IN)

    # ── ⑤ KO source lane(§8·EN run 과 분리) ──
    ko_lane = build_ko_source_lane(probe_fn=probe_fn)

    # ── ⑥ sanitized snapshot(§F) — live 미실행이면 작성 대상 없음. live 실행돼도 snapshot 작성은 별도 ADR 로 이연 ──
    sanitized_snapshot_status = (
        "not_written_no_live_run" if not live_executed else "not_written_deferred")
    sanitized_live_snapshot_written = False

    # ── ⑦ blocked reason(§5) — date-pin 미충족이 binding. date-pin 후엔 query-wiring 미구현, 그 후 live 미승인 ──
    query_wiring_blocks = date_pinned and not LIVE_QUERY_TARGET_WIRED
    binding_block = (
        BLOCKED_MISSING_DATE_PIN if not date_pinned
        else BLOCKED_QUERY_WIRING if query_wiring_blocks
        else LIVE_BLOCKED_NO_OPT_IN if not live_executed else "")
    block_reasons = list(dict.fromkeys([
        *( [BLOCKED_MISSING_DATE_PIN] if not date_pinned else [] ),
        *( [BLOCKED_QUERY_WIRING] if query_wiring_blocks else [] ),
        *( [LIVE_BLOCKED_NO_OPT_IN] if (not live_executed and date_pinned and not query_wiring_blocks) else [] ),
        *(base.get("block_reasons") or []),
    ]))
    acquisition_next_action = (
        "provide_or_select_date_pinned_event then request bounded live run approval (host/rate honored · 1~2 seeds max)"
        if not date_pinned
        else ("wire date-pinned event into the live query path (operator-confirmed dated event → exact query) "
              "before live run") if query_wiring_blocks
        else "approve_bounded_live_run (date-pinned · host/rate honored)" if not live_executed
        else "review_live_recall_classification and attempt production candidate freeze")
    next_actions = list(dict.fromkeys([
        acquisition_next_action,
        f"pin selected seed '{named_seed_selected}' to an actual occurrence date (operator confirms event happened)",
        ko_lane["ko_next_action"],
        *(base.get("next_actions") or []),
    ]))

    out = {
        "operation_name": BOUNDED_OPERATION_NAME,
        "batch_id": batch_id,
        # actual input 재확인(§3-A·base passthrough).
        "actual_input_rechecked": base.get("actual_input_rechecked"),
        "actual_contact_evidence_found": base.get("actual_contact_evidence_found"),
        "actual_returned_labels_found": base.get("actual_returned_labels_found"),
        "actual_input_status": base.get("actual_input_status"),
        # ADR#81 커밋(이번 턴 §1 안정 기준점).
        "adr81_committed": True,
        # named seed date-pin(§5).
        "named_seed_selected": named_seed_selected,
        "named_seed_date_pinned": date_pinned,
        "named_seed_date_pin_status": named_seed_date_pin_status,
        "selected_seed_actual_occurrence": selected_seed_actual_occurrence,
        "date_pin_rejection_reasons": date_pin["rejection_reasons"],
        # bounded live(§3-B·§6·§7).
        "live_query_approved": bool(live_query),
        "live_query_executed": live_executed,
        "live_query_target_wired": LIVE_QUERY_TARGET_WIRED,   # 정직: pinned event→실 쿼리 배선 미구현(fail-closed).
        "live_run_status": live_run_status,
        "live_call_count": base.get("live_call_count") or 0,
        "host_gate_respected": True,             # no-bypass; 이 경로는 live 미호출(wiring False)이라 vacuously true.
        "rate_limit_respected": True,
        "providers_used": (base.get("providers_used") or []) if live_executed else [],
        "provider_breadth_used": pool["provider_breadth_used"],
        "key_free_provider_count": pool["key_free_provider_count"],
        "credential_required_provider_count": pool["credential_required_provider_count"],
        "bounded_live_provider_pool": pool["bounded_live_provider_pool"],
        "providers_in_pool": pool["providers_in_pool"],
        "query_capable_not_yet_wired": pool["query_capable_not_yet_wired"],
        "comparison_pair_count": base.get("comparison_pair_count") or 0,
        "max_baseline_jaccard": round(float(base.get("max_baseline_jaccard") or 0.0), 4),
        "max_recall_probe_score": base.get("max_live_recall_probe_score") or 0.0,
        "live_pairs_newly_routed_by_probe": base.get("live_pairs_newly_routed_by_probe") or 0,
        "live_pairs_sharing_entity_after_probe": base.get("live_pairs_sharing_entity_after_probe") or 0,
        # production candidate freeze(§3-D·§7·base passthrough·freeze-only-live-derived·둔갑 0).
        "production_candidate_status": base.get("production_candidate_status") or "blocked",
        "production_candidate_batch_ready": bool(base.get("production_candidate_batch_ready")),
        "production_batch_id": base.get("production_batch_id") or batch_id,
        "production_frozen_pair_count": base.get("production_frozen_pair_count") or 0,
        "candidate_provenance": base.get("candidate_provenance"),
        # sanitized snapshot(§F).
        "sanitized_live_snapshot_written": sanitized_live_snapshot_written,
        "sanitized_snapshot_status": sanitized_snapshot_status,
        # KO source lane(§3-E·§8).
        "ko_source_lane_status": ko_lane["ko_source_lane_status"],
        "ko_named_seed_needed": ko_lane["ko_named_seed_needed"],
        "ko_adapter_next_action": ko_lane["ko_next_action"],
        "ko_floor_current": ko_lane["ko_floor_current"],
        "ko_floor_required": ko_lane["ko_floor_required"],
        "ko_source_lane": ko_lane,
        # acquisition frontier(§3-F·§9·sanitized).
        "acquisition_frontier_ui_ready": True,
        # community reaction contract(§3-G·docs·runtime 0).
        "community_reaction_contract_preserved": True,
        # R1 gap(base passthrough).
        "production_gold_count": base.get("production_gold_count") or 0,
        "current_r1_gap": base.get("current_r1_gap") or 0,
        "r2_r7_no_go": True,
        # source role guard(breadth pool + KO).
        "source_role_guard_preserved": bool(
            pool["source_role_guard_preserved"] and base.get("source_role_guard_preserved")
            and ko_lane["source_role_guard_preserved"]),
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
        "binding_block_reason": binding_block,
        "blocked_reason": binding_block,
        "acquisition_next_action": acquisition_next_action,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    out["internal_ops_bounded_live_breadth_frontier"] = build_bounded_live_breadth_frontier(out=out)
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·드리프트 fail-loud).
    _assert_pii_safe(out, _path="r1_bounded_live_breadth_run_output")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#82 bounded live breadth run + date-pin gate + production candidate freeze attempt "
                     "(merge 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0; 기본 live 미실행·date-pin 미충족 차단)."))
    parser.add_argument("--batch-id", default=PROD_BATCH_ID, help="production-candidate freeze batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument("--live-query", action="store_true",
                        help="명시적 opt-in: bounded date-pinned live fetch(network·승인+date-pin 시만·값 미노출).")
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

    out = run_bounded_live_breadth_run(
        directory=ns.input_dir, batch_id=ns.batch_id, as_of=ns.as_of,
        live_query=ns.live_query, host_gate=host_gate)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: status={out['actual_input_status']} returned_labels={out['actual_returned_labels_found']}")
    print(f"- named_seed: selected={out['named_seed_selected']} date_pinned={out['named_seed_date_pinned']} "
          f"status={out['named_seed_date_pin_status']} occurrence={out['selected_seed_actual_occurrence']}")
    print(f"- bounded_pool: breadth_used={out['provider_breadth_used']} key_free={out['key_free_provider_count']} "
          f"cred_required={out['credential_required_provider_count']} in_pool={out['providers_in_pool']}")
    print(f"    query_capable_not_yet_wired={out['query_capable_not_yet_wired']}")
    print(f"- live: approved={out['live_query_approved']} executed={out['live_query_executed']} "
          f"status={out['live_run_status']} call_count={out['live_call_count']} "
          f"comparison_pairs={out['comparison_pair_count']} max_score={out['max_recall_probe_score']}")
    print(f"- production_candidate: status={out['production_candidate_status']} provenance={out['candidate_provenance']} "
          f"frozen={out['production_frozen_pair_count']} ready={out['production_candidate_batch_ready']}")
    print(f"- ko_lane: status={out['ko_source_lane_status']} named_seed_needed={out['ko_named_seed_needed']} "
          f"floor={out['ko_floor_current']}/{out['ko_floor_required']}")
    print(f"- snapshot: written={out['sanitized_live_snapshot_written']} status={out['sanitized_snapshot_status']}")
    print(f"- r1_gap: production_gold={out['production_gold_count']} gap={out['current_r1_gap']} "
          f"r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- gates: merge={out['merge_allowed']} llm={out['llm_invoked']} embedding={out['embedding_invoked']} "
          f"db_write={out['db_write']} sending={out['actual_sending_performed']} "
          f"public_iu={not out['no_public_intelligence_unit']}")
    print(f"- blocked_reason: {out['blocked_reason']}")
    print(f"- next_action: {out['acquisition_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
