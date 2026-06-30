"""ADR#82/#83 — bounded live breadth run + named-event date-pin gate + date-pinned live query plumbing
+ production-candidate freeze attempt (merge 0 · LLM 0 · embedding 0 · DB 0 · 전송 0 · secret read 0 · public IU 0).

ADR#82 는 provider breadth → 실제 bounded live pool 을 정직히 산출하고 date-pin 게이트를 걸었으나, operator 가 핀한
event 를 *실제 쿼리 대상* 으로 꽂는 plumbing 이 없어 `LIVE_QUERY_TARGET_WIRED=False` 로 fail-closed 했다(Finding 1:
승인된 event X ≠ 쿼리되는 curated event Y). ADR#83 은 그 배선을 `live_query_target.py` 에 격리해 해소한다:
  - operator date-pinned event(named_entity + event_phrase + occurrence_date) → `build_live_query_target` 로 정확한
    query_text + 절대 윈도우 [D, D+1] 를 만들고(§B·§6),
  - 승인 + wired 시 `execute_date_pinned_bounded_live_run`(검증된 targeted-layer 패턴 미러)으로 operator query 를
    실제 쿼리해 live-derived 후보를 얻고 production candidate freeze 를 시도한다(§C·§D·§7·§8).
  - operator event 가 없으면(이번 턴) base(ADR#81/#82) passthrough 로 동작을 보존하고 blocked 를 정직히 산출한다
    (blocked_reason=missing_operator_date_pinned_event·§1).

이번 턴 정책(§3): A(actual input 재확인)+B(date-pinned query plumbing·**test-lock**)+C(executor wiring·operator event
미제공 → live 미실행)+D 조건부(live 없음 → freeze 없음·코드만 무장)+E(KO lane)+F 설계(snapshot 미작성)+G(community
contract). H 분석만·I(LLM/RAG/KG/public IU runtime) 금지.

절대 불변: merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret 값 0 · public IU 0 · same_event 단정 0 · production
gold 0. provider breadth=acquisition support not truth · date-pin=operator gate not occurrence proof · operator query
=실제 쿼리 대상(curated fallback 둔갑 0) · freeze=reviewer worklist not truth · community=reaction only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Callable, Optional

# ADR#90/#91 product-vision contracts(read API 안전: 전부 pure 또는 status 주입·real payload path 미독·network 0).
# authoring helper/sourcing workflow 는 curated seed + 주입 status 기반(`operator_regulatory_event_payload` 의 상수/순수
# 헬퍼[REAL_PAYLOAD_PATH·is_example_payload·validate]만 전이 사용·real-path **리더** resolve_/load_ 에는 도달 0 — sourcing
# workflow 는 operator_payload_status 를 주입받아 disk read 0). taxonomy/overlap diagnostics/hot-post gate/community roadmap/
# 3 contract 는 pure. r1_label_return_operational_bridge 는 dropbox readiness + r1_gold_acquisition_plan 합성(gitignored
# outputs/ 스캔·network 0)이며 **real-path 를 읽는 `operator_confirmed_live_runner` 는 어느 ADR#91 모듈도 미import** →
# GET 이 live/real-path 미접촉(전이 그래프에 operator payload 디스크 리더 0).
from backend.app.tools.agent_hotness_reasoning_contract import (
    build_agent_hotness_reasoning_contract,
)
from backend.app.tools.community_interaction_future_gate import (
    build_community_interaction_future_gate,
)
from backend.app.tools.community_posting_roadmap_contract import (
    build_community_posting_roadmap_contract,
)
from backend.app.tools.hot_intelligence_post_contract import (
    build_hot_intelligence_post_contract,
)
from backend.app.tools.hot_post_gate_alignment import build_hot_post_gate_alignment
from backend.app.tools.ko_source_readiness import build_ko_source_lane
from backend.app.tools.live_no_yield_taxonomy import build_live_no_yield_taxonomy
from backend.app.tools.live_query_target import (
    build_live_query_target,
    execute_date_pinned_bounded_live_run,
)
from backend.app.tools.official_news_label_intake_readiness import (
    run_official_news_label_intake_readiness,
)
from backend.app.tools.official_news_overlap_diagnostics import (
    build_official_news_overlap_diagnostics,
)
from backend.app.tools.operator_payload_authoring_helper import (
    build_operator_payload_authoring,
)
from backend.app.tools.operator_payload_sourcing_workflow import (
    build_operator_payload_sourcing_workflow,
)
from backend.app.tools.r1_label_return_operational_bridge import (
    build_r1_label_return_operational_bridge,
)
from backend.app.tools.r1_production_candidate_acquisition import PROD_BATCH_ID
from backend.app.tools.r1_provider_breadth_acquisition import (
    run_provider_breadth_named_seed_ko_path,
)
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.returned_label_dropbox_readiness import (
    build_returned_label_dropbox_readiness,
)
from backend.app.tools.reviewer_contact_launch_checklist import (
    build_reviewer_contact_launch_checklist,
)
from backend.app.tools.reviewer_contact_readiness import build_reviewer_contact_readiness
from backend.app.tools.reviewer_handoff_bridge import build_reviewer_handoff_bridge
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe
from backend.app.tools.sanitized_live_snapshot import (
    build_sanitized_live_snapshot,
    write_sanitized_live_snapshot,
)
from backend.app.tools.window_honoring_source_readiness import (
    build_window_honoring_source_readiness,
)

BOUNDED_OPERATION_NAME = "bounded_live_breadth_run_and_candidate_freeze_attempt"
DATE_PINNED_OPERATION_NAME = "date_pinned_live_query_and_freeze_attempt"

# ── binding blocker 어휘(§7 classify) ─────────────────────────────────────────────────────────────────────
# operator event 미제공(§1) — 이번 턴의 binding blocker.
BLOCKED_MISSING_OPERATOR_EVENT = "missing_operator_date_pinned_event"
# operator event 는 있으나 date-pin shape 무효(occurrence_date 부재/비-ISO·broad·placeholder).
BLOCKED_INVALID_DATE_PIN = "invalid_date_pinned_event"
# date-pin 유효하나 live query target 미wired(LIVE_QUERY_TARGET_WIRED False 또는 provider pool 부족) — fail-closed.
BLOCKED_TARGET_NOT_WIRED = "live_query_target_not_wired"
# §7 live 미승인.
LIVE_BLOCKED_NO_OPT_IN = "blocked_no_live_opt_in"
# live 승인+wired 이나 fetch 게이트(credential/host).
BLOCKED_NO_CREDENTIALS = "blocked_no_credentials"
BLOCKED_HOST_GATE = "blocked_host_gate"
# live 실행됐으나 후보 0 분해(§7).
LIVE_NO_RESULTS = "live_no_results"
LIVE_NO_CROSS_SOURCE_PAIRS = "live_no_cross_source_pairs"
LIVE_NO_ROUTING_CANDIDATES = "live_no_routing_candidates"
# live 후보/동결(§7·blocked 아님).
LIVE_CANDIDATES_FOUND = "live_candidates_found"
PRODUCTION_BATCH_FROZEN = "production_batch_frozen"

# ── back-compat 상수(ADR#82 importer 보존) ──────────────────────────────────────────────────────────────────
# ADR#82 의 seed-기반 date-pin blocker. ADR#83 은 operator-event 기반(BLOCKED_MISSING_OPERATOR_EVENT)으로 전환하나,
# 상수는 정의를 유지(외부 importer 호환). 더 이상 default 경로의 binding 이 아니다.
BLOCKED_MISSING_DATE_PIN = "missing_date_pinned_named_event"
# ADR#82 의 query-wiring 미구현 blocker. ADR#83 에서 wiring 이 test-lock 되어 LIVE_QUERY_TARGET_WIRED=True 가 되면서
# 이 binding 은 BLOCKED_TARGET_NOT_WIRED 로 대체된다(상수 정의는 호환 유지).
BLOCKED_QUERY_WIRING = "date_pinned_query_wiring_not_implemented"

# r1_production_candidate_acquisition 6-state → ADR#83 live_run_status 매핑(§7 vocabulary).
_PCAND_TO_LIVE_STATUS = {
    "production_batch_frozen": PRODUCTION_BATCH_FROZEN,
    "live_candidates_found": LIVE_CANDIDATES_FOUND,
    "blocked_no_live_overlap": LIVE_NO_CROSS_SOURCE_PAIRS,
    "blocked_no_publishable_pairs": LIVE_NO_ROUTING_CANDIDATES,
    "blocked_no_credentials": BLOCKED_NO_CREDENTIALS,
    "blocked_no_live_opt_in": LIVE_BLOCKED_NO_OPT_IN,
}

# §10 ADR#82 bounded live breadth frontier 필수 정직 copy(원형 유지·해당 frontier 전용).
BOUNDED_LIVE_REQUIRED_COPY: tuple[str, ...] = (
    "Provider breadth is acquisition support, not truth",
    "Named seed is candidate generation, not same-event proof",
    "A bounded live run requires an operator-confirmed date-pinned event",
    "Community reaction is not an event anchor",
    "Production candidate freeze is a reviewer worklist, not same-event truth",
    "Production gold remains 0 until human labels are returned",
    "R2~R7 remain No-Go",
)

# §13 ADR#83 date-pinned live run frontier 필수 정직 copy(date-pin + query target + freeze 경계 명시).
DATE_PINNED_REQUIRED_COPY: tuple[str, ...] = (
    "A date-pinned operator event is required before any bounded live run",
    "occurrence_date is an operator assertion, not a code-verified fact",
    "A date pin does not prove the event occurred or that both sources cover it",
    "The live query targets the operator event, never a curated seed fallback",
    "Provider date parameters are not trusted until verified by a control experiment",
    "Out-of-window records cannot become production candidates",
    "Federal Register is official evidence, not a news article",
    "Official-news bridge is reviewer-routing only, not same-event truth",
    "Official record alone is not a production cross-source candidate",
    "A regulatory-class seed needs an agency/entity, an action, and a confirmed date window",
    "Operator confirmation is required before live regulatory acquisition",
    "Reviewer contact readiness is not actual sending",
    "Provide an operator-confirmed regulatory event payload before live acquisition",
    "Returned label dropbox readiness is not production gold",
    "Production candidate freeze is a reviewer worklist, not same-event truth",
    "Production gold remains 0 until human labels are returned",
    # ADR#90 product-vision copy(community-style intelligence post 방향·runtime 은 gate 전 No-Go).
    "This project targets a community-style intelligence web product, not a raw news feed",
    "Hot Intelligence Post runtime remains disabled until evidence, gold, and merge gates pass",
    "Community reaction is reaction_to only, not an evidence anchor",
    # ADR#91 — sourcing workflow + no-yield diagnostics + hot-post gate + label-return agreement gate copy.
    "Operator must provide a real confirmed payload before live acquisition",
    "Live no-yield results are actionable diagnostics, not failure endpoints",
    "Hot Post public runtime requires R1/R2 gates",
    "Returned labels are not gold until agreement gates pass",
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
    """§9 internal ops bounded live breadth frontier(ADR#82·sanitized·read-only·public truth 아님).

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


def build_date_pinned_live_run_frontier(*, out: dict) -> dict:
    """§11 internal ops date-pinned live run frontier(ADR#83·sanitized·read-only·public truth 아님).

    operator event provided·date-pin status·live query target wired·live executed·providers·comparison/recall
    aggregate·production candidate status·snapshot·KO lane·blocked·next_action·R1 gap·R2~R7 No-Go·정직 copy 만.
    same_event truth·per-pair score·rationale·predicted_status·raw body·PII·secret·named_entity/event_phrase 전문은
    필드 자체가 없어 구조적 미노출(_assert_pii_safe 재귀 가드 + 스키마 화이트리스트)."""
    return {
        "contract": "InternalOpsDatePinnedLiveRunFrontier",
        "latest_date_pinned_live_run_status": out["live_run_status"],
        "operator_event_provided": bool(out["operator_event_provided"]),
        "occurrence_date": out["occurrence_date"],
        "occurrence_date_valid_iso": bool(out["occurrence_date_valid_iso"]),
        "date_pinned_named_event_valid": bool(out["named_seed_date_pinned"]),
        "live_query_target_wired": bool(out["live_query_target_wired"]),
        "live_query_approved": bool(out["live_query_approved"]),
        "live_query_executed": bool(out["live_query_executed"]),
        "live_call_count": int(out["live_call_count"] or 0),
        "providers_used": list(out["providers_used"] or []),
        "comparison_pair_count": int(out["comparison_pair_count"] or 0),
        "max_recall_probe_score": round(float(out["max_recall_probe_score"] or 0.0), 4),
        "newly_routed_count": int(out["live_pairs_newly_routed_by_probe"] or 0),
        "production_candidate_status": out["production_candidate_status"] or "blocked",
        "production_candidate_batch_ready": bool(out["production_candidate_batch_ready"]),
        "production_frozen_pair_count": int(out["production_frozen_pair_count"] or 0),
        "candidate_provenance": out["candidate_provenance"] or "none",
        "sanitized_snapshot_status": out["sanitized_snapshot_status"],
        "date_window_enforced": bool(out["date_window_enforced"]),
        "reviewer_handoff_ready": bool(out["reviewer_handoff_ready"]),
        # ADR#85 date-window fidelity(§12·sanitized·메커니즘은 confidence 와 함께·단정 0).
        "provider_date_window_fidelity_status": out["provider_date_window_fidelity_status"],
        "control_experiment_status": out["control_experiment_status"],
        "date_filter_mechanism_primary": out["date_filter_mechanism_primary"],
        "date_filter_mechanism_confidence": out["date_filter_mechanism_confidence"],
        "out_of_window_records_dropped": int(out["out_of_window_records_dropped"] or 0),
        "window_honoring_source_status": out["window_honoring_source_status"],
        # ADR#86 FR adapter/live + official×news bridge(§13·sanitized·aggregate-only·score 0·body 0).
        "federal_register_adapter_status": out["federal_register_adapter_status"],
        "federal_register_live_status": out["federal_register_live_status"],
        "federal_register_date_filter_capability": out["federal_register_date_filter_capability"],
        "official_news_bridge_status": out["official_news_bridge_status"],
        "official_records_count": int(out["official_records_count"] or 0),
        "news_records_count": int(out["news_records_count"] or 0),
        "bridge_candidate_count": int(out["bridge_candidate_count"] or 0),
        "official_news_freeze_eligible_count": int(out["official_news_freeze_eligible_count"] or 0),
        # ADR#87 regulatory seed bank + official×news live acquisition(sanitized·aggregate-only).
        "regulatory_seed_bank_status": out["regulatory_seed_bank_status"],
        "selected_regulatory_seed_id": out["selected_regulatory_seed_id"],
        "official_news_live_status": out["official_news_live_status"],
        "official_news_production_candidate_status": out["official_news_production_candidate_status"],
        "official_news_reviewer_handoff_ready": bool(out["official_news_reviewer_handoff_ready"]),
        # ADR#88 operator-confirmed event intake + reviewer contact readiness + label intake readiness(sanitized).
        "operator_event_status": out["operator_event_status"],
        "operator_confirmed": bool(out["operator_confirmed"]),
        "confirmation_valid": bool(out["confirmation_valid"]),
        "confirmation_blocked_reason": out["confirmation_blocked_reason"],
        "reviewer_contact_ready": bool(out["reviewer_contact_ready"]),
        "label_intake_readiness_status": out["label_intake_readiness_status"],
        # ADR#89 operator payload entrypoint + returned label dropbox readiness + reviewer contact launch checklist.
        # operator payload=real(gitignored)/example(committed) 분리·live-run gate; dropbox=수신 경로/schema 준비(실 label
        # 전까지 production gold 0); contact launch checklist=수동 접촉 직전(actual sending 0).
        "operator_payload_status": out["operator_payload_status"],
        "operator_payload_path_status": out["operator_payload_path_status"],
        "label_dropbox_ready": bool(out["label_dropbox_ready"]),
        "actual_returned_label_count": int(out["actual_returned_label_count"] or 0),
        "reviewer_contact_checklist_ready": bool(out["reviewer_contact_checklist_ready"]),
        # ADR#90 product-vision contracts(payload authoring next action + live no-yield taxonomy + hot-post/hotness/
        # community gate·runtime-disabled·sanitized 문자열/bool 만·public post/comment runtime No-Go).
        "operator_payload_template_ready": bool(out["operator_payload_template_ready"]),
        "operator_payload_next_action": out["operator_payload_next_action"],
        "live_no_yield_taxonomy_status": out["live_no_yield_taxonomy_status"],
        "hot_intelligence_post_contract_status": out["hot_intelligence_post_contract_status"],
        "agent_hotness_contract_status": out["agent_hotness_contract_status"],
        "community_interaction_gate_status": out["community_interaction_gate_status"],
        # ADR#91 sourcing workflow + overlap diagnostics + R1 label-return bridge + hot-post gate + community roadmap
        # (sanitized·runtime-disabled·real payload 미독·public post/comment runtime No-Go). 행동 가능한 next_action 노출.
        "payload_sourcing_status": out["payload_sourcing_status"],
        "payload_sourcing_next_action": out["payload_sourcing_next_action"],
        "taxonomy_next_action": out["taxonomy_next_action"],
        "overlap_diagnostic_status": out["overlap_diagnostic_status"],
        "overlap_blocked_dimension": out["overlap_blocked_dimension"],
        "r1_label_return_status": out["r1_label_return_status"],
        "r1_label_return_next_action": out["r1_label_return_next_action"],
        "hot_post_gate_status": out["hot_post_gate_status"],
        "hot_post_public_readiness": bool(out["hot_post_public_readiness"]),
        "community_posting_roadmap_status": out["community_posting_roadmap_status"],
        "ko_source_lane_status": out["ko_source_lane_status"],
        "ko_named_seed_needed": bool(out["ko_named_seed_needed"]),
        "ko_floor_current": int(out["ko_floor_current"] or 0),
        "ko_floor_required": int(out["ko_floor_required"] or 0),
        "blocked_reason": out["blocked_reason"] or "",
        "acquisition_next_action": out["acquisition_next_action"],
        "current_r1_gap": int(out["current_r1_gap"] or 0),
        "production_gold_count": int(out["production_gold_count"] or 0),
        "r2_r7_no_go": True,
        "required_copy": list(DATE_PINNED_REQUIRED_COPY),
        "flags": {"no_public_truth": True, "no_same_event_truth": True, "no_score": True,
                  "no_rationale": True, "no_predicted_status": True, "no_raw_body": True,
                  "no_secret": True},
    }


def _classify_binding(
    *, operator_event_provided: bool, date_pinned: bool, target: dict, live_query: bool,
    live_executed: bool, smoke: Optional[dict], pcand: Optional[dict],
) -> tuple[str, str]:
    """(binding_block, live_run_status) 산출(§7·정직·둔갑 0).

    pre-live 게이트(operator event/date-pin/wiring/opt-in) 우선, 그 다음 fetch 게이트(credential/host), 그 다음 live
    결과(no results/no cross-source/no routing/candidates/frozen). binding_block="" 는 성공(freeze/candidates)이며
    blocked 가 아님."""
    if not operator_event_provided:
        return BLOCKED_MISSING_OPERATOR_EVENT, BLOCKED_MISSING_OPERATOR_EVENT
    if not date_pinned:
        return BLOCKED_INVALID_DATE_PIN, BLOCKED_INVALID_DATE_PIN
    if not target.get("wired"):
        return BLOCKED_TARGET_NOT_WIRED, BLOCKED_TARGET_NOT_WIRED
    if not live_query:
        return LIVE_BLOCKED_NO_OPT_IN, LIVE_BLOCKED_NO_OPT_IN
    sm = smoke or {}
    pc = pcand or {}
    brs = sm.get("block_reasons") or []
    if not live_executed:
        # executor 가 fetch 전/중 게이트(credential/host) 또는 결과 0.
        if "host_gate_blocked" in brs:
            return BLOCKED_HOST_GATE, BLOCKED_HOST_GATE
        st = pc.get("production_candidate_status")
        if st == "blocked_no_credentials":
            return BLOCKED_NO_CREDENTIALS, BLOCKED_NO_CREDENTIALS
        if any(b.startswith("no_records") for b in brs):
            return LIVE_NO_RESULTS, LIVE_NO_RESULTS
        # credential present 인데 비-credential 사유(rate_limit/network 등)로 fetch 미성공 → live_no_results 정직
        # (st==blocked_no_credentials 는 위에서 이미 return·여기 도달 시 credential 결손 아님).
        return LIVE_NO_RESULTS, LIVE_NO_RESULTS
    # live 실행됨 — pcand 6-state → §7 status.
    st = pc.get("production_candidate_status") or ""
    live_status = _PCAND_TO_LIVE_STATUS.get(st, st or LIVE_NO_RESULTS)
    if live_status in (PRODUCTION_BATCH_FROZEN, LIVE_CANDIDATES_FOUND):
        return "", live_status   # 성공 — blocked 아님.
    return live_status, live_status


def _acquisition_next_action(binding: str, *, target: dict, named_seed_selected: Optional[str]) -> str:
    """binding blocker → operator 한 줄 next action(internal ops UI 가 읽는 단일 요약·secret 0·PII 0)."""
    if binding == BLOCKED_MISSING_OPERATOR_EVENT:
        return ("operator must provide a date-pinned event (named_entity + event_phrase + occurrence_date ISO) — "
                f"suggested seed to pin: '{named_seed_selected}' (operator confirms the actual occurrence date)")
    if binding == BLOCKED_INVALID_DATE_PIN:
        return ("fix the date-pinned event before a live run: "
                f"{','.join(target.get('block_reasons') or []) or 'invalid'} "
                "(occurrence_date must be ISO YYYY-MM-DD; entity/phrase must not be a broad umbrella)")
    if binding == BLOCKED_TARGET_NOT_WIRED:
        return ("live query target not wired or provider pool insufficient (need guardian + 1 wired publishable "
                "provider with credentials present)")
    if binding == LIVE_BLOCKED_NO_OPT_IN:
        return ("approve a bounded live run (live_query=True / --live-query) — the operator event is valid and the "
                "query target is wired (host/rate honored · raw body 0 · secret 0)")
    if binding == BLOCKED_NO_CREDENTIALS:
        return ("set the provider credentials (GUARDIAN_API_KEY/NYT_API_KEY) in .env (secret 커밋 금지·값 미노출) "
                "before the bounded live run")
    if binding == BLOCKED_HOST_GATE:
        return "respect the shared host floor (no-bypass); retry after min_spacing"
    if binding in (LIVE_NO_RESULTS, LIVE_NO_CROSS_SOURCE_PAIRS, LIVE_NO_ROUTING_CANDIDATES):
        return ("live run returned no production candidate — broaden the window/providers or pin a higher cross-source "
                "coverage event (two outlets must report the same dated event)")
    return ("live-derived publishable candidates found — distribute the frozen production-candidate worklist to >=2 "
            "pseudonymous reviewers per pair and collect returned label JSONL; production gold stays 0 until labels import")


def _snapshot_run_id(target: dict) -> str:
    """sanitized snapshot run_id(결정론·secret 0) — occurrence_date + query_text 해시(원문 미노출·재현 식별만)."""
    seed = f"{target.get('occurrence_date')}|{target.get('query_text')}"
    return "datepin_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _fr_adapter_status(readiness: dict) -> str:
    """readiness 후보 행에서 federal_register adapter_status('wired'/'not_wired') 추출(ADR#86)."""
    for r in readiness.get("candidates") or []:
        if r.get("source_id") == "federal_register":
            return r.get("adapter_status") or "unknown"
    return "unknown"


def _adr86_official_news_fields(
    *, readiness: dict, fr_live_result: Optional[dict], bridge_result: Optional[dict],
) -> dict:
    """ADR#86 sanitized frontier 필드(FR adapter/live + official×news bridge·aggregate-only·secret 0·body 0).

    fr_live_result(federal_register_live_smoke) 주입 시 live status/date_filter_capability 노출, 없으면 not_run/
    documented_unverified. bridge_result(official_news_role_bridge) 주입 시 bridge status/count, 없으면 모듈은
    구축·테스트 완료이나 이번 턴 live in-window pair 미생성(bridge_built_not_run). raw title/url/score 0."""
    frl = fr_live_result or {}
    br = bridge_result or {}
    fr_dfc = frl.get("date_filter_capability") or "documented_unverified"
    if bridge_result:
        bridge_status = (
            "freeze_eligible_bridge_candidates" if int(br.get("freeze_eligible_bridge_count") or 0) > 0
            else (br.get("blocked_reason") or "no_official_news_bridge_candidate"))
    else:
        bridge_status = "bridge_built_not_run"   # 모듈 구축·테스트 완료·이번 턴 live in-window official×news pair 0.
    return {
        "federal_register_adapter_status": _fr_adapter_status(readiness),
        "federal_register_live_status": frl.get("fr_live_status") or "not_run",
        "federal_register_date_filter_capability": fr_dfc,
        "official_news_bridge_status": bridge_status,
        "official_records_count": int(frl.get("in_window_records") or 0),
        "news_records_count": int(br.get("news_record_count") or 0),
        "bridge_candidate_count": int(br.get("bridge_candidate_count") or 0),
        "official_news_freeze_eligible_count": int(br.get("freeze_eligible_bridge_count") or 0),
    }


def _adr87_official_news_acquisition_fields(*, acq: Optional[dict], bank: dict) -> dict:
    """ADR#87 sanitized frontier 필드(regulatory seed bank + official×news live acquisition·aggregate-only·secret 0).

    bank(regulatory_event_seed_bank)는 network 0 라 항상 산출(seed bank readiness + selected seed). acq
    (official_news_live_acquisition) 주입 시 live status/production candidate/handoff 노출, 없으면 not_run(이번 턴
    operator 가 official×news live 미실행). raw title/url/score 0."""
    a = acq or {}
    return {
        "regulatory_seed_bank_status": "ready" if bank.get("regulatory_event_seed_bank_ready") else "not_ready",
        "selected_regulatory_seed_id": bank.get("selected_seed_id"),
        "official_news_live_status": a.get("official_news_live_status") or "not_run",
        "official_news_production_candidate_status": a.get("production_candidate_status") or "blocked",
        "official_news_reviewer_handoff_ready": bool(a.get("reviewer_handoff_ready")),
    }


def _adr88_operator_intake_fields(
    *, operator_intake: Optional[dict], contact_readiness: dict, label_intake_readiness: dict,
) -> dict:
    """ADR#88 sanitized frontier 필드(operator-confirmed event intake + reviewer contact readiness + official×news
    label intake readiness·aggregate-only·secret 0·score 0).

    operator_intake(`run_operator_regulatory_event_intake`) 주입 시 confirmation status 노출, 없으면 not_provided
    (이번 턴 operator 가 confirmed event 미제공). contact_readiness 는 handoff 파생(freeze 없으면 ready=False).
    label_intake_readiness 는 network 0·항상 산출(synthetic dry-run·production gold 0)."""
    oi = operator_intake or {}
    cr = contact_readiness or {}
    li = label_intake_readiness or {}
    return {
        "operator_event_status": oi.get("operator_event_status") or "not_provided",
        "operator_confirmed": bool(oi.get("operator_confirmed")),
        "confirmation_valid": bool(oi.get("confirmation_valid")),
        "confirmation_blocked_reason": oi.get("confirmation_blocked_reason") or "",
        "reviewer_contact_ready": bool(cr.get("reviewer_contact_ready")),
        "label_intake_readiness_status": li.get("label_intake_readiness_status") or "not_run",
    }


def _adr89_operator_payload_dropbox_fields(
    *, payload_entrypoint: Optional[dict], dropbox_readiness: dict, launch_checklist: dict,
) -> dict:
    """ADR#89 sanitized frontier 필드(operator payload entrypoint + returned label dropbox readiness + reviewer
    contact launch checklist·aggregate-only·secret 0·score 0·raw payload 0).

    payload_entrypoint(`operator_regulatory_event_payload.resolve_operator_payload_entrypoint`) 주입 시 real payload
    status 노출, 없으면 not_provided(read API 는 real path 를 읽지 않아 live 미실행). dropbox_readiness·launch_checklist
    는 network 0·항상 산출(dropbox=synthetic schema dry-run·실 label 0·gold 0; checklist=freeze 없으면 launch 미준비)."""
    pe = payload_entrypoint or {}
    db = dropbox_readiness or {}
    lc = launch_checklist or {}
    return {
        "operator_payload_status": pe.get("operator_payload_status") or "not_provided",
        "operator_payload_path_status": pe.get("operator_payload_path_status") or "example_only_no_real_payload",
        "label_dropbox_ready": bool(db.get("label_dropbox_ready")),
        "actual_returned_label_count": int(db.get("actual_returned_label_count") or 0),
        "reviewer_contact_checklist_ready": bool(lc.get("reviewer_contact_launch_ready")),
    }


# ADR#90 contract status 어휘(runtime disabled·contract only — frontier 노출용 sanitized 문자열).
_CONTRACT_READY_RUNTIME_DISABLED = "contract_ready_runtime_disabled"


def _adr90_product_contract_fields(*, operator_payload_status: str, official_news_live_status: str) -> dict:
    """ADR#90 sanitized frontier 필드(payload authoring + live no-yield taxonomy + hot-post/hotness/community contract).

    전부 **pure**(network 0·real payload path 미독): authoring helper 는 curated seed→fillable 템플릿(operator next
    action), taxonomy 는 payload_status+engine status→세분 분류, 3 contract 는 runtime-disabled 계약 상태. read API 가
    이 헬퍼를 거쳐도 live/real-path 를 건드리지 않는다(Hot-Post/comment runtime 은 gate 전 No-Go)."""
    auth = build_operator_payload_authoring()
    tax = build_live_no_yield_taxonomy(
        {"official_news_live_status": official_news_live_status},
        payload_entrypoint_out={"operator_payload_status": operator_payload_status})
    hp = build_hot_intelligence_post_contract()
    hn = build_agent_hotness_reasoning_contract()
    cg = build_community_interaction_future_gate()
    return {
        "operator_payload_template_ready": bool(auth.get("payload_template_ready")),
        "operator_payload_next_action": auth.get("next_action") or "",
        "live_no_yield_taxonomy_status": tax.get("live_no_yield_taxonomy_status") or "not_run",
        "hot_intelligence_post_contract_status": (
            _CONTRACT_READY_RUNTIME_DISABLED if not hp.get("runtime_enabled") else "runtime_enabled"),
        "agent_hotness_contract_status": (
            _CONTRACT_READY_RUNTIME_DISABLED if not hn.get("runtime_enabled") else "runtime_enabled"),
        "community_interaction_gate_status": (
            cg.get("community_interaction_gate_status") or "community_interaction_requirements_unmet"),
    }


def _adr91_product_ops_fields(
    *, operator_payload_status: str, official_news_live_status: str, dropbox: dict, batch_id: str,
) -> dict:
    """ADR#91 sanitized frontier 필드(payload sourcing workflow + overlap diagnostics + R1 label-return bridge +
    hot-post gate alignment + community posting roadmap).

    read API 안전: sourcing workflow 는 operator_payload_status 를 **주입**받아 real path 미독(disk read 0); overlap
    diagnostics/hot-post gate/community roadmap 은 pure; r1_label_return_bridge 는 이미 계산된 dropbox 를 주입받고
    r1_gold_acquisition_plan 으로 gitignored outputs/ 만 스캔한다(network 0·live runner 미경유·real payload 미독)."""
    sourcing = build_operator_payload_sourcing_workflow(operator_payload_status=operator_payload_status)
    overlap = build_official_news_overlap_diagnostics()   # 후보 없음 → not_run.
    r1_return = build_r1_label_return_operational_bridge(batch_id=batch_id, dropbox_readiness=dropbox)
    hp_gate = build_hot_post_gate_alignment()             # 빈 draft → blocked_requirements_unmet.
    roadmap = build_community_posting_roadmap_contract()
    tax = build_live_no_yield_taxonomy(
        {"official_news_live_status": official_news_live_status},
        payload_entrypoint_out={"operator_payload_status": operator_payload_status})
    return {
        "payload_sourcing_status": sourcing["payload_sourcing_status"],
        "payload_sourcing_next_action": sourcing["next_action"],
        "taxonomy_next_action": tax["current"]["next_action"],
        "overlap_diagnostic_status": overlap["overlap_diagnostic_status"],
        "overlap_blocked_dimension": overlap.get("blocked_dimension") or "",
        "r1_label_return_status": r1_return["r1_label_return_status"],
        "r1_label_return_next_action": r1_return["next_action"],
        "hot_post_gate_status": hp_gate["hot_post_gate_status"],
        "hot_post_public_readiness": bool(hp_gate["public_readiness"]),
        "community_posting_roadmap_status": roadmap["community_posting_roadmap_status"],
    }


def run_bounded_live_breadth_run(
    *, directory: Optional[Any] = None, batch_id: str = PROD_BATCH_ID, as_of: Optional[str] = None,
    live_query: bool = False, operator_event: Optional[dict] = None, pinned_event: Optional[dict] = None,
    base_result: Optional[dict] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    probe_fn: Optional[Callable[[str], dict]] = None,
    transport_factory: Optional[Callable[[str, str], Optional[Callable[[str], Optional[str]]]]] = None,
    transport_a: Optional[Callable[[str], Optional[str]]] = None,
    transport_b: Optional[Callable[[str], Optional[str]]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None, host_gate: Any = None,
    readiness_fn: Optional[Callable[[], dict]] = None, gate_fn: Optional[Callable[..., dict]] = None,
    synthetic_batch_fn: Optional[Callable[..., dict]] = None,
    persist_snapshot: bool = False,
    fidelity_result: Optional[dict] = None,
    federal_register_live_result: Optional[dict] = None,
    official_news_bridge_result: Optional[dict] = None,
    official_news_acquisition_result: Optional[dict] = None,
    operator_event_intake_result: Optional[dict] = None,
    reviewer_contact_readiness_result: Optional[dict] = None,
    official_news_label_intake_readiness_result: Optional[dict] = None,
    operator_payload_entrypoint_result: Optional[dict] = None,
    returned_label_dropbox_readiness_result: Optional[dict] = None,
    reviewer_contact_launch_checklist_result: Optional[dict] = None,
) -> dict:
    """ADR#82/#83/#84 단일 진입 — base(breadth/seed/KO/actual-input) + date-pin gate + date-pinned live executor +
    freeze + reviewer handoff bridge + sanitized snapshot.

    operator_event(또는 back-compat pinned_event) 가 valid date-pinned event 이고 live_query 승인 + target.wired 일
    때만 `execute_date_pinned_bounded_live_run` 로 operator query 를 실제 쿼리해 live-derived 후보 freeze 를 시도한다.
    셋 중 하나라도 미충족이면 base 를 live 미실행으로 호출(네트워크 0)하고 blocked 정직 산출 — 이번 턴 기본
    operator_event=None → blocked_reason=missing_operator_date_pinned_event. base_result 주입 시 base 재실행 생략
    (orchestrator 단위 테스트용). transport_a/transport_b/env_probe_fn 주입 시 live executor 결정론(network 0).
    merge 0 · LLM 0 · embedding 0 · DB 0 · 전송 0 · secret read 0 · same_event 0 · gold 0."""
    operator_event = operator_event if operator_event is not None else pinned_event

    # ── ① base(ADR#81/#82 — breadth/seed/KO/actual-input). live_query=False 로 호출(date-pinned live 는 별도 executor) ──
    base = base_result if base_result is not None else run_provider_breadth_named_seed_ko_path(
        directory=directory, batch_id=batch_id, as_of=as_of, live_query=False,
        env_status_fn=env_status_fn, probe_fn=probe_fn, transport_factory=transport_factory,
        env_probe_fn=env_probe_fn, host_gate=host_gate, readiness_fn=readiness_fn,
        gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)

    sel = base.get("selected_seed_for_next_live_run")
    named_seed_selected = sel.get("seed_id") if isinstance(sel, dict) else sel

    # ── ② bounded live pool(§6) — breadth inventory → 실제 실행가능 교집합(정직) ──
    pool = build_bounded_live_provider_pool(base.get("provider_breadth_inventory") or [])

    # ── ③ date-pinned live query target(§B·live_query_target·PURE·network 0) — operator_event=None → not provided ──
    # 실제 실행가능 pool 을 그대로 전달(빈 리스트도 전달→`build_live_query_target` 이 BLOCK_PROVIDER_POOL_EMPTY 정직
    # 발화; `or None` 폴백 제거 — adversarial F1: 0-provider 를 default [guardian,nyt] 로 마스킹해 wired 과대보고 방지).
    target = build_live_query_target(operator_event, provider_pool=pool["providers_in_pool"])
    date_pinned = bool(target["date_pinned_named_event_valid"])
    operator_event_provided = bool(target["operator_event_provided"])
    selected_seed_actual_occurrence = target["occurrence_date"]
    named_seed_date_pin_status = (
        f"pinned:{selected_seed_actual_occurrence}" if date_pinned
        else f"not_pinned:{','.join(target['block_reasons']) or 'unknown'}")

    # ── ④ live eligibility(§7) — live_query 승인 ∧ target.wired(date_pinned ∧ WIRED ∧ providers≥2·guardian anchor) ──
    live_eligible = bool(live_query) and bool(target["wired"])
    smoke: Optional[dict] = None
    pcand: Optional[dict] = None
    if live_eligible:
        live_result = execute_date_pinned_bounded_live_run(
            target, directory=directory, batch_id=batch_id, as_of=as_of,
            transport_a=transport_a, transport_b=transport_b, env_status_fn=env_status_fn,
            env_probe_fn=env_probe_fn, host_gate=host_gate, readiness_fn=readiness_fn,
            gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)
        smoke = live_result.get("smoke")
        pcand = live_result.get("pcand")
        live_executed = bool(live_result.get("executed"))
        live_call_count = int(live_result.get("live_call_count") or 0)
    else:
        # base passthrough(ADR#82 — operator event 없음/미승인/미wired 시 base 동작 보존).
        live_executed = bool(base.get("live_query_executed"))
        live_call_count = int(base.get("live_call_count") or 0)

    # ── ⑤ live/freeze fields — executor 실행 시 smoke/pcand, 아니면 base passthrough ──
    if live_eligible and (smoke is not None or pcand is not None):
        sm = smoke or {}
        pc = pcand or {}
        recall = sm.get("recall_probe_diagnostic") or {}
        band = sm.get("band_diagnostic") or {}
        comparison_pair_count = int(sm.get("cross_source_pair_count") or 0)
        max_recall_probe_score = float(recall.get("max_recall_probe_score") or 0.0)
        live_pairs_newly_routed = int(recall.get("pairs_newly_routed_by_probe") or 0)
        live_pairs_sharing_entity = int(recall.get("pairs_newly_routed_sharing_entity") or 0)
        max_baseline_jaccard = float(band.get("max_cross_source_title_jaccard") or 0.0)
        providers_used = list(sm.get("providers") or target["providers"])
        production_candidate_status = pc.get("production_candidate_status") or "blocked"
        production_candidate_batch_ready = bool(pc.get("production_candidate_batch_ready"))
        production_batch_id = pc.get("production_batch_id") or batch_id
        production_frozen_pair_count = int(pc.get("production_frozen_pair_count") or 0)
        candidate_provenance = pc.get("candidate_provenance") or "none"
        production_gold_count = int(pc.get("production_gold_count") or 0)
        current_r1_gap = int(pc.get("current_r1_gap") or 0)
        actual_input_status = pc.get("actual_input_status") or base.get("actual_input_status")
        score_exposed = bool(pc.get("score_exposed"))
        rationale_exposed = bool(pc.get("rationale_exposed"))
        predicted_status_exposed = bool(pc.get("predicted_status_exposed"))
        raw_pii_exposed = bool(pc.get("raw_pii_exposed"))
        merge_allowed = bool(pc.get("merge_allowed"))
        db_write = bool(pc.get("db_write"))
        llm_invoked = bool(pc.get("llm_invoked"))
        embedding_invoked = bool(pc.get("embedding_invoked"))
        host_gate_respected = "host_gate_blocked" not in (sm.get("block_reasons") or [])
        rate_limit_respected = "rate_limited" not in (sm.get("block_reasons") or [])
        actual_sending_performed = bool(pc.get("actual_sending_performed"))
        base_block_reasons = list(pc.get("block_reasons") or [])
        base_next_actions = list(pc.get("next_actions") or [])
    else:
        comparison_pair_count = int(base.get("comparison_pair_count") or 0)
        max_recall_probe_score = float(base.get("max_live_recall_probe_score") or 0.0)
        live_pairs_newly_routed = int(base.get("live_pairs_newly_routed_by_probe") or 0)
        live_pairs_sharing_entity = int(base.get("live_pairs_sharing_entity_after_probe") or 0)
        max_baseline_jaccard = float(base.get("max_baseline_jaccard") or 0.0)
        providers_used = (base.get("providers_used") or []) if live_executed else []
        production_candidate_status = base.get("production_candidate_status") or "blocked"
        production_candidate_batch_ready = bool(base.get("production_candidate_batch_ready"))
        production_batch_id = base.get("production_batch_id") or batch_id
        production_frozen_pair_count = int(base.get("production_frozen_pair_count") or 0)
        candidate_provenance = base.get("candidate_provenance") or "none"
        production_gold_count = int(base.get("production_gold_count") or 0)
        current_r1_gap = int(base.get("current_r1_gap") or 0)
        actual_input_status = base.get("actual_input_status")
        score_exposed = bool(base.get("score_exposed"))
        rationale_exposed = bool(base.get("rationale_exposed"))
        predicted_status_exposed = bool(base.get("predicted_status_exposed"))
        raw_pii_exposed = bool(base.get("raw_pii_exposed"))
        merge_allowed = bool(base.get("merge_allowed"))
        db_write = bool(base.get("db_write"))
        llm_invoked = bool(base.get("llm_invoked"))
        embedding_invoked = bool(base.get("embedding_invoked"))
        host_gate_respected = True             # 이 경로는 live 미호출(executor 미실행)이라 vacuously true.
        rate_limit_respected = True
        actual_sending_performed = False
        base_block_reasons = list(base.get("block_reasons") or [])
        base_next_actions = list(base.get("next_actions") or [])

    # ── ⑥ KO source lane(§8·EN run 과 분리) ──
    ko_lane = build_ko_source_lane(probe_fn=probe_fn)

    # ── ⑧ binding classifier(§7) + next action ──
    binding_block, live_run_status = _classify_binding(
        operator_event_provided=operator_event_provided, date_pinned=date_pinned, target=target,
        live_query=live_query, live_executed=live_executed, smoke=smoke, pcand=pcand)
    acquisition_next_action = _acquisition_next_action(
        binding_block, target=target, named_seed_selected=named_seed_selected)
    block_reasons = list(dict.fromkeys([
        *( [binding_block] if binding_block else [] ),
        *base_block_reasons,
    ]))
    next_actions = list(dict.fromkeys([
        acquisition_next_action,
        f"pin selected seed '{named_seed_selected}' to an actual occurrence date (operator confirms event happened)",
        ko_lane["ko_next_action"],
        *base_next_actions,
    ]))

    # ── ⑨ sanitized live snapshot(§E·ADR#84) — live 실행 시 build; persist_snapshot 시 outputs/(gitignored) write ──
    # date_window_enforced: executor 는 enforce_window=True 로 호출(provider 가 out-of-window 기사를 반환해도 adapter 가
    # [D, D+1] 밖 record 를 drop) — ADR#84 live run 이 plumbing 은 맞으나 provider 가 window 를 무시함을 발견한 데 대한 보정.
    date_window_enforced = bool(live_eligible)
    executor_out = {"executed": live_executed, "live_call_count": live_call_count,
                    "smoke": smoke, "pcand": pcand}
    snapshot = build_sanitized_live_snapshot(
        target, executor_out, run_id=_snapshot_run_id(target), live_run_status=live_run_status,
        date_window_enforced=date_window_enforced, fidelity_result=fidelity_result,
        federal_register_live_result=federal_register_live_result,
        official_news_bridge_result=official_news_bridge_result)
    if not live_executed:
        sanitized_snapshot_status = "not_written_no_live_run"
        sanitized_live_snapshot_written = False
        sanitized_live_snapshot_path = ""
    elif persist_snapshot:
        w = write_sanitized_live_snapshot(snapshot)
        sanitized_snapshot_status = w["snapshot_status"]
        sanitized_live_snapshot_written = w["snapshot_status"] == "written"
        sanitized_live_snapshot_path = w["snapshot_path"]
    else:
        # live 실행됐으나 비-persist(orchestrator 단위 테스트·API read 경로): 작성 안 함(disk side-effect 0).
        sanitized_snapshot_status = "built_not_persisted"
        sanitized_live_snapshot_written = False
        sanitized_live_snapshot_path = ""

    # ── ⑩ reviewer handoff bridge(§7·ADR#84·freeze→contact 직전·전송 0) — freeze 없으면 ready=False(blocker 표면화) ──
    handoff = build_reviewer_handoff_bridge(pcand or {}, live_run_status=live_run_status)
    reviewer_handoff_ready = bool(handoff["reviewer_handoff_ready"])

    # ── ⑪ ADR#85 date-window fidelity 보강 — readiness 는 pure(항상)·control experiment 결과는 주입 시에만 ──
    # fidelity_result(provider_date_window_fidelity.run_date_window_fidelity_probe) 가 있으면 메커니즘/symptom 을
    # frontier 에 노출; 없으면 control_experiment_pending(단정 0). window-honoring readiness 는 network 0(FR 권고).
    readiness = build_window_honoring_source_readiness()
    _fr = fidelity_result or {}
    _fid_executed = bool(_fr.get("live_query_executed"))
    provider_date_window_fidelity_status = (
        (_fr.get("provider_date_window_status") or "executed") if _fid_executed
        else "control_experiment_pending")
    window_honoring_source_status = (
        f"{readiness['recommended_adapter']}_adapter_wired" if readiness.get("adapter_wired_this_turn")
        else (f"{readiness['recommended_adapter']}_recommended_adr86" if readiness.get("recommended_adapter")
              else "no_window_honoring_candidate"))
    # ── ADR#86: FR adapter/live + official×news bridge sanitized 필드(주입 시 live·없으면 not_run/built_not_run) ──
    # ADR#87: official_news_acquisition_result 주입 시 그 안의 FR live + bridge sub-result 를 ADR#86 필드 소스로
    # 사용(직접 주입 federal_register_live_result/official_news_bridge_result 가 우선·둘 다 없으면 acq 에서 파생).
    _acq = official_news_acquisition_result or {}
    _fr_live_src = federal_register_live_result or _acq.get("federal_register_live_result")
    _bridge_src = official_news_bridge_result or _acq.get("official_news_bridge_result")
    _adr86 = _adr86_official_news_fields(
        readiness=readiness, fr_live_result=_fr_live_src, bridge_result=_bridge_src)
    # ── ADR#87: regulatory seed bank(network 0·항상) + official×news live acquisition status(주입 시·없으면 not_run) ──
    _reg_bank = build_regulatory_event_seed_bank()
    _adr87 = _adr87_official_news_acquisition_fields(acq=official_news_acquisition_result, bank=_reg_bank)
    # ── ADR#88: operator-confirmed event intake(주입 시·없으면 not_provided) + reviewer contact readiness(handoff
    # 파생·freeze 없으면 ready=False) + official×news label intake readiness(network 0·항상·synthetic dry-run·gold 0) ──
    _contact_readiness = reviewer_contact_readiness_result or build_reviewer_contact_readiness(handoff)
    _label_intake_readiness = (
        official_news_label_intake_readiness_result or run_official_news_label_intake_readiness())
    _adr88 = _adr88_operator_intake_fields(
        operator_intake=operator_event_intake_result,
        contact_readiness=_contact_readiness, label_intake_readiness=_label_intake_readiness)
    # ── ADR#89: operator payload entrypoint(주입 시·없으면 not_provided — read API 는 real gitignored path 를 읽지 않아
    # live 미실행) + returned label dropbox readiness(network 0·항상·dropbox=synthetic schema dry-run·실 label 0·gold 0)
    # + reviewer contact launch checklist(contact readiness ∧ dropbox readiness·freeze 없으면 launch 미준비·전송 0) ──
    # ADR#90 §15·GAP4 — run batch_id 를 dropbox 와 launch checklist 양쪽에 전파(수신 경로와 worklist 가 같은 batch).
    _dropbox = returned_label_dropbox_readiness_result or build_returned_label_dropbox_readiness(
        batch_id=batch_id, label_readiness=_label_intake_readiness)
    _launch_checklist = reviewer_contact_launch_checklist_result or build_reviewer_contact_launch_checklist(
        contact_readiness=_contact_readiness, dropbox_readiness=_dropbox, batch_id=batch_id)
    _adr89 = _adr89_operator_payload_dropbox_fields(
        payload_entrypoint=operator_payload_entrypoint_result,
        dropbox_readiness=_dropbox, launch_checklist=_launch_checklist)
    # ADR#90 — product-vision contract 상태(payload authoring next action + live no-yield taxonomy + hot-post/hotness/
    # community gate). 전부 pure(network 0·real path 미독) — read API 가 거쳐도 live/real-path 미접촉.
    _adr90 = _adr90_product_contract_fields(
        operator_payload_status=_adr89["operator_payload_status"],
        official_news_live_status=_adr87["official_news_live_status"])
    # ADR#91 — sourcing workflow + overlap diagnostics + R1 label-return bridge + hot-post gate + community roadmap.
    # sourcing 은 status 주입(real path 미독)·overlap/gate/roadmap pure·r1_return 은 이미 만든 _dropbox 주입(중복 스캔 0).
    _adr91 = _adr91_product_ops_fields(
        operator_payload_status=_adr89["operator_payload_status"],
        official_news_live_status=_adr87["official_news_live_status"],
        dropbox=_dropbox, batch_id=batch_id)

    out = {
        "operation_name": BOUNDED_OPERATION_NAME,
        "date_pinned_operation_name": DATE_PINNED_OPERATION_NAME,
        "batch_id": batch_id,
        # actual input 재확인(§3-A·base passthrough).
        "actual_input_rechecked": base.get("actual_input_rechecked"),
        "actual_contact_evidence_found": base.get("actual_contact_evidence_found"),
        "actual_returned_labels_found": base.get("actual_returned_labels_found"),
        "actual_input_status": actual_input_status,
        "adr81_committed": True,
        # operator event / date-pin(§B·§5·§6).
        "operator_event_provided": operator_event_provided,
        "named_seed_selected": named_seed_selected,
        "named_seed_date_pinned": date_pinned,
        "named_seed_date_pin_status": named_seed_date_pin_status,
        "named_entity": target["named_entity"],
        "event_phrase": target["event_phrase"],
        "occurrence_date": target["occurrence_date"],
        "occurrence_date_valid_iso": bool(target["occurrence_date_valid_iso"]),
        "selected_seed_actual_occurrence": selected_seed_actual_occurrence,
        "date_pin_rejection_reasons": target["block_reasons"],
        "event_occurrence_verified": False,
        "same_event_asserted": False,
        # live query target(§6·live_query_target).
        "live_query_target_wired": bool(target["live_query_target_wired"]),
        "live_query_text": target["query_text"],
        "live_query_start_date": target["start_date"],
        "live_query_end_date": target["end_date"],
        "live_query_as_of_anchor": target["as_of_anchor"],
        "live_query_time_window": target["time_window"],
        "live_query_providers": target["providers"],
        "live_query_source_role_required": target["source_role_required"],
        # bounded live(§3-B·§6·§7).
        "live_query_approved": bool(live_query),
        "live_query_executed": live_executed,
        "live_run_status": live_run_status,
        "live_call_count": live_call_count,
        "host_gate_respected": host_gate_respected,
        "rate_limit_respected": rate_limit_respected,
        "providers_used": providers_used,
        "provider_breadth_used": pool["provider_breadth_used"],
        "key_free_provider_count": pool["key_free_provider_count"],
        "credential_required_provider_count": pool["credential_required_provider_count"],
        "bounded_live_provider_pool": pool["bounded_live_provider_pool"],
        "providers_in_pool": pool["providers_in_pool"],
        "query_capable_not_yet_wired": pool["query_capable_not_yet_wired"],
        "comparison_pair_count": comparison_pair_count,
        "max_baseline_jaccard": round(max_baseline_jaccard, 4),
        "max_recall_probe_score": max_recall_probe_score,
        "live_pairs_newly_routed_by_probe": live_pairs_newly_routed,
        "live_pairs_sharing_entity_after_probe": live_pairs_sharing_entity,
        # production candidate freeze(§3-D·§7·§8·live-derived 만·둔갑 0).
        "production_candidate_status": production_candidate_status,
        "production_candidate_batch_ready": production_candidate_batch_ready,
        "production_batch_id": production_batch_id,
        "production_frozen_pair_count": production_frozen_pair_count,
        "candidate_provenance": candidate_provenance,
        # sanitized snapshot(§E·ADR#84) + date window enforcement.
        "sanitized_live_snapshot_written": sanitized_live_snapshot_written,
        "sanitized_live_snapshot_path": sanitized_live_snapshot_path,
        "sanitized_snapshot_status": sanitized_snapshot_status,
        "date_window_enforced": date_window_enforced,
        # reviewer handoff bridge(§7·ADR#84·freeze→contact 직전·전송 0·freeze 없으면 ready=False).
        "reviewer_handoff_ready": reviewer_handoff_ready,
        "reviewer_handoff_bridge": handoff,
        "expected_label_files_ready": bool(handoff["expected_label_files_ready"]),
        "validation_command_ready": bool(handoff["validation_command_ready"]),
        "placement_guide_ready": bool(handoff["placement_guide_ready"]),
        # ADR#85 date-window fidelity(control experiment + window-honoring readiness·sanitized·§12).
        "provider_date_window_fidelity_status": provider_date_window_fidelity_status,
        "control_experiment_status": "executed" if _fid_executed else "not_run",
        "date_filter_mechanism_primary": _fr.get("mechanism_primary_hypothesis") or "undetermined",
        "date_filter_mechanism_confidence": _fr.get("mechanism_confidence") or "none",
        "out_of_window_records_dropped": int(_fr.get("out_of_window_records_dropped") or 0),
        "window_honoring_source_status": window_honoring_source_status,
        "next_adapter_for_adr86": readiness.get("next_adapter_for_adr86"),
        "window_honoring_source_readiness": readiness,
        "provider_date_window_fidelity": fidelity_result,
        # ADR#86 FR adapter/live + official×news bridge(sanitized·§13·aggregate-only·secret 0·body 0·score 0).
        "federal_register_adapter_status": _adr86["federal_register_adapter_status"],
        "federal_register_live_status": _adr86["federal_register_live_status"],
        "federal_register_date_filter_capability": _adr86["federal_register_date_filter_capability"],
        "official_news_bridge_status": _adr86["official_news_bridge_status"],
        "official_records_count": _adr86["official_records_count"],
        "news_records_count": _adr86["news_records_count"],
        "bridge_candidate_count": _adr86["bridge_candidate_count"],
        "official_news_freeze_eligible_count": _adr86["official_news_freeze_eligible_count"],
        # ADR#87 regulatory seed bank + official×news live acquisition(sanitized·aggregate-only·secret 0·score 0).
        "regulatory_seed_bank_status": _adr87["regulatory_seed_bank_status"],
        "selected_regulatory_seed_id": _adr87["selected_regulatory_seed_id"],
        "official_news_live_status": _adr87["official_news_live_status"],
        "official_news_production_candidate_status": _adr87["official_news_production_candidate_status"],
        "official_news_reviewer_handoff_ready": _adr87["official_news_reviewer_handoff_ready"],
        # ADR#88 operator-confirmed event intake + reviewer contact readiness + label intake readiness(sanitized).
        "operator_event_status": _adr88["operator_event_status"],
        "operator_confirmed": _adr88["operator_confirmed"],
        "confirmation_valid": _adr88["confirmation_valid"],
        "confirmation_blocked_reason": _adr88["confirmation_blocked_reason"],
        "reviewer_contact_ready": _adr88["reviewer_contact_ready"],
        "label_intake_readiness_status": _adr88["label_intake_readiness_status"],
        # ADR#89 operator payload entrypoint + returned label dropbox readiness + reviewer contact launch checklist
        # (sanitized·aggregate-only·raw payload 0·secret 0·score 0). payload not_provided=read API 는 real path 미독.
        "operator_payload_status": _adr89["operator_payload_status"],
        "operator_payload_path_status": _adr89["operator_payload_path_status"],
        "label_dropbox_ready": _adr89["label_dropbox_ready"],
        "actual_returned_label_count": _adr89["actual_returned_label_count"],
        "reviewer_contact_checklist_ready": _adr89["reviewer_contact_checklist_ready"],
        # ADR#90 product-vision contracts(payload authoring next action + live no-yield taxonomy + hot-post/hotness/
        # community gate·전부 runtime-disabled contract·pure·real path 미독). community-style intelligence post 방향 정렬.
        "operator_payload_template_ready": _adr90["operator_payload_template_ready"],
        "operator_payload_next_action": _adr90["operator_payload_next_action"],
        "live_no_yield_taxonomy_status": _adr90["live_no_yield_taxonomy_status"],
        "hot_intelligence_post_contract_status": _adr90["hot_intelligence_post_contract_status"],
        "agent_hotness_contract_status": _adr90["agent_hotness_contract_status"],
        "community_interaction_gate_status": _adr90["community_interaction_gate_status"],
        # ADR#91 sourcing workflow + overlap diagnostics + R1 label-return bridge + hot-post gate + community roadmap
        # (sanitized 문자열/bool·runtime-disabled·real payload 미독·public post/comment runtime No-Go). operator 가
        # 다음에 무엇을 채우고/고치고/import 할지를 행동 가능한 next_action 으로 노출(상용 운영자 관점).
        "payload_sourcing_status": _adr91["payload_sourcing_status"],
        "payload_sourcing_next_action": _adr91["payload_sourcing_next_action"],
        "taxonomy_next_action": _adr91["taxonomy_next_action"],
        "overlap_diagnostic_status": _adr91["overlap_diagnostic_status"],
        "overlap_blocked_dimension": _adr91["overlap_blocked_dimension"],
        "r1_label_return_status": _adr91["r1_label_return_status"],
        "r1_label_return_next_action": _adr91["r1_label_return_next_action"],
        "hot_post_gate_status": _adr91["hot_post_gate_status"],
        "hot_post_public_readiness": _adr91["hot_post_public_readiness"],
        "community_posting_roadmap_status": _adr91["community_posting_roadmap_status"],
        # KO source lane(§3-E·§8).
        "ko_source_lane_status": ko_lane["ko_source_lane_status"],
        "ko_named_seed_needed": ko_lane["ko_named_seed_needed"],
        "ko_adapter_next_action": ko_lane["ko_next_action"],
        "ko_floor_current": ko_lane["ko_floor_current"],
        "ko_floor_required": ko_lane["ko_floor_required"],
        "ko_source_lane": ko_lane,
        # acquisition frontier(§3-F·§9·§11·sanitized).
        "acquisition_frontier_ui_ready": True,
        # community reaction contract(§3-G·docs·runtime 0).
        "community_reaction_contract_preserved": True,
        # R1 gap(passthrough).
        "production_gold_count": production_gold_count,
        "current_r1_gap": current_r1_gap,
        "r2_r7_no_go": True,
        # source role guard(breadth pool + KO + base).
        "source_role_guard_preserved": bool(
            pool["source_role_guard_preserved"] and base.get("source_role_guard_preserved")
            and ko_lane["source_role_guard_preserved"]),
        # 안전 경계(정직·constant + 파생).
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "score_exposed": score_exposed,
        "rationale_exposed": rationale_exposed,
        "predicted_status_exposed": predicted_status_exposed,
        "raw_pii_exposed": raw_pii_exposed,
        "raw_source_body_exposed": False,
        "no_public_intelligence_unit": True,
        "merge_allowed": merge_allowed,
        "db_write": db_write,
        "llm_invoked": llm_invoked,
        "embedding_invoked": embedding_invoked,
        "actual_sending_performed": actual_sending_performed,
        "binding_block_reason": binding_block,
        "blocked_reason": binding_block,
        "acquisition_next_action": acquisition_next_action,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    out["internal_ops_bounded_live_breadth_frontier"] = build_bounded_live_breadth_frontier(out=out)
    out["internal_ops_date_pinned_live_run_frontier"] = build_date_pinned_live_run_frontier(out=out)
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·드리프트 fail-loud).
    _assert_pii_safe(out, _path="r1_bounded_live_breadth_run_output")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#82/#83 bounded live breadth run + date-pinned live query plumbing + production candidate "
                     "freeze attempt (merge 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0; operator event + "
                     "--live-query 없으면 live 미실행)."))
    parser.add_argument("--batch-id", default=PROD_BATCH_ID, help="production-candidate freeze batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument("--operator-named-entity", default="", help="operator named entity(예: 'US Federal Reserve').")
    parser.add_argument("--operator-event-phrase", default="", help="operator event 행위(예: 'FOMC rate decision').")
    parser.add_argument("--operator-occurrence-date", default="", help="실제 발생일 ISO YYYY-MM-DD(operator 확인).")
    parser.add_argument("--live-query", action="store_true",
                        help="명시적 opt-in: bounded date-pinned live fetch(network·승인+date-pin+wiring 시만·값 미노출).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    operator_event = None
    if ns.operator_named_entity or ns.operator_event_phrase or ns.operator_occurrence_date:
        operator_event = {
            "named_entity": ns.operator_named_entity, "event_phrase": ns.operator_event_phrase,
            "occurrence_date": ns.operator_occurrence_date,
        }

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
        live_query=ns.live_query, operator_event=operator_event, host_gate=host_gate,
        persist_snapshot=ns.live_query)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} / {out['date_pinned_operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: status={out['actual_input_status']} returned_labels={out['actual_returned_labels_found']}")
    print(f"- operator_event: provided={out['operator_event_provided']} date_pinned={out['named_seed_date_pinned']} "
          f"occurrence={out['occurrence_date']} status={out['named_seed_date_pin_status']}")
    print(f"- query_target: wired={out['live_query_target_wired']} text={out['live_query_text']!r} "
          f"window=[{out['live_query_start_date']},{out['live_query_end_date']}] providers={out['live_query_providers']}")
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
    print(f"- snapshot: written={out['sanitized_live_snapshot_written']} status={out['sanitized_snapshot_status']} "
          f"date_window_enforced={out['date_window_enforced']}")
    print(f"- handoff_bridge: ready={out['reviewer_handoff_ready']} "
          f"actual_sending={out['actual_sending_performed']}")
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
