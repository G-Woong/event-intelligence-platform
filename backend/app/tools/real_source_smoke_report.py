"""ADR#55 — real-source smoke 종합 report: activation report 병합 + source quality matrix + agent readiness 9조건.

**순수·결정론**(DB/network 미접근) — smoke 결과 dict + db_target 분류를 입력으로 §4 report fields / §8 readiness /
§9 source quality matrix 를 조립한다. **fabrication 0**(입력에 없는 수치를 만들지 않음). no_auto_merge 불변.
source role guard 보존(community/market/catalog 는 anchor 아님 — guard_only 로 분리). 본문/PII 미포함.
"""
from __future__ import annotations

from typing import Any, Optional

from backend.app.services.event_ingest_pipeline import _RECORD_TYPE_TO_SOURCE_TYPE
from backend.app.tools.db_target import classify_write_target

# identity anchor / 본문 기대 source_type(event_ingest_pipeline._IDENTITY_ANCHOR_SOURCE_TYPES 와 정합).
_PUBLISHABLE_SOURCE_TYPES = frozenset({"official", "article"})
_BODY_EXPECTED_SOURCE_TYPES = frozenset({"official", "article"})       # document/article = 산문 본문 기대
# structured_signal→"signal"·catalog_metadata→"catalog"(_RECORD_TYPE_TO_SOURCE_TYPE): 메타/수치 = 본문 미추출 실패 아님.
_METADATA_COMPLETE_SOURCE_TYPES = frozenset({"signal", "catalog"})


def _source_type_for_record(rec: dict) -> str:
    return _RECORD_TYPE_TO_SOURCE_TYPE.get(rec.get("record_type"), "unknown")


# §8 overlap potential / source role utility(ADR#57): role 별 결정론 라벨 — Agent 가 source 별 처리전략을
# (anchor / reaction / signal / enrichment) 선택할 substrate. overlap_potential 은 cross-source same-event
# 가능성(official=문서 distinct·뉴스=wire 다출처). community/market/catalog 는 anchor 아님(역할만 보존).
_ROLE_UTILITY: dict[str, dict[str, Any]] = {
    "official": {
        "overlap_potential": "document_distinct_low_overlap",   # 1문서=1URL=1사건 → cross-source 희소
        "same_event_discovery_utility": "low_official_distinct",
        "official_confirmation_utility": "high",
        "time_series_update_utility": "medium",
        "agent_utility": "merge_anchor",
        "community_reaction_layer_eligible": False,
        "market_signal_utility": "none", "catalog_entity_enrichment_utility": "none",
        # ADR#58 §9: overlap acquisition 관점(실측 근거). official 은 문서 distinct → pairability 낮음.
        "title_paraphrase_risk": "low_distinct_document",
        "overlap_acquisition_utility": "low_official_distinct",
        "cross_source_pairability": "distinct_low_pairable",
        "same_event_likelihood": "low_structurally_distinct",
        "body_policy": "store_headline_canonical_only_no_body",
    },
    "article": {
        "overlap_potential": "wire_syndication_capable",        # 다출처 wire verbatim/paraphrase → overlap 생성원
        "same_event_discovery_utility": "high_multi_outlet",
        "official_confirmation_utility": "medium",
        "time_series_update_utility": "high",
        "agent_utility": "merge_anchor",
        "community_reaction_layer_eligible": False,
        "market_signal_utility": "none", "catalog_entity_enrichment_utility": "none",
        # ADR#58 §9: 실측(RSS 다출처 55 record·same-beat 30 record → title overlap 0) — paraphrase 지배·
        # untargeted feed 는 overlap 희소. targeting(topic/time/same-event query) 필요.
        "title_paraphrase_risk": "high_paraphrase_dominant",
        "overlap_acquisition_utility": "high_but_requires_targeting",
        "cross_source_pairability": "multi_outlet_pairable",
        "same_event_likelihood": "targeted_high_untargeted_low",
        "body_policy": "store_headline_canonical_only_no_body",
    },
    "community": {
        "overlap_potential": "reaction_not_anchor",
        "same_event_discovery_utility": "none_reaction_layer",
        "official_confirmation_utility": "none",
        "time_series_update_utility": "low",
        "agent_utility": "reaction_layer",
        "community_reaction_layer_eligible": True,
        "market_signal_utility": "none", "catalog_entity_enrichment_utility": "none",
        "title_paraphrase_risk": "n/a_reaction_layer",
        "overlap_acquisition_utility": "none_reaction_not_anchor",
        "cross_source_pairability": "not_pairable_anchor_forbidden",
        "same_event_likelihood": "n/a_reaction_layer",
        "body_policy": "reaction_signal_no_body_anchor",
    },
    "signal": {
        "overlap_potential": "signal_not_anchor",
        "same_event_discovery_utility": "none_signal_layer",
        "official_confirmation_utility": "none",
        "time_series_update_utility": "high",
        "agent_utility": "market_signal",
        "community_reaction_layer_eligible": False,
        "market_signal_utility": "high", "catalog_entity_enrichment_utility": "none",
        "title_paraphrase_risk": "n/a_structured_signal",
        "overlap_acquisition_utility": "none_signal_not_anchor",
        "cross_source_pairability": "not_pairable_anchor_forbidden",
        "same_event_likelihood": "n/a_signal_layer",
        "body_policy": "structured_metadata_no_body",
    },
    "catalog": {
        "overlap_potential": "enrichment_not_anchor",
        "same_event_discovery_utility": "none_enrichment_layer",
        "official_confirmation_utility": "none",
        "time_series_update_utility": "low",
        "agent_utility": "entity_enrichment",
        "community_reaction_layer_eligible": False,
        "market_signal_utility": "none", "catalog_entity_enrichment_utility": "high",
        "title_paraphrase_risk": "n/a_catalog_metadata",
        "overlap_acquisition_utility": "none_enrichment_not_anchor",
        "cross_source_pairability": "not_pairable_anchor_forbidden",
        "same_event_likelihood": "n/a_enrichment_layer",
        "body_policy": "structured_metadata_no_body",
    },
    "search": {
        "overlap_potential": "url_candidate_not_anchor",
        "same_event_discovery_utility": "none_url_candidate",
        "official_confirmation_utility": "none",
        "time_series_update_utility": "low",
        "agent_utility": "url_candidate",
        "community_reaction_layer_eligible": False,
        "market_signal_utility": "none", "catalog_entity_enrichment_utility": "none",
        "title_paraphrase_risk": "downstream_resolved",
        "overlap_acquisition_utility": "url_candidate_pre_resolution",
        "cross_source_pairability": "post_resolution_only",
        "same_event_likelihood": "downstream_resolved",
        "body_policy": "url_candidate_no_body_until_resolved",
    },
}
_ROLE_UTILITY_UNKNOWN: dict[str, Any] = {
    "overlap_potential": "unknown", "same_event_discovery_utility": "unknown",
    "official_confirmation_utility": "none", "time_series_update_utility": "unknown",
    "agent_utility": "fail_closed", "community_reaction_layer_eligible": False,
    "market_signal_utility": "none", "catalog_entity_enrichment_utility": "none",
    "title_paraphrase_risk": "unknown", "overlap_acquisition_utility": "unknown",
    "cross_source_pairability": "unknown", "same_event_likelihood": "unknown",
    "body_policy": "fail_closed_no_body",
}


# ADR#58 §9: source-level acquisition 제약(provider/rate-limit/robots). role 로 일반화 못 하는 운영 사실은
# **하드 근거가 있는 source 만** 명시하고 나머지는 unknown(fabrication 0). 근거: rate_limit_policy.yaml(gdelt
# 429·min 60s·cooldown 900s), source_registry auth=none(key-free), source_strategy_memory(gdelt no_bypass).
_ACQUISITION_PROFILE: dict[str, dict[str, str]] = {
    "gdelt": {
        "provider_accessibility": "key_free_but_rate_limited",
        "rate_limit_risk": "high_provider_429",            # 실측·rate_limit_policy gdelt cooldown 900s
        "robots_tos_status": "public_api_no_bypass",
    },
    "rss": {                                                # key-free RSS 함대(bbc/aljazeera/yna/…·auth=none)
        "provider_accessibility": "key_free_rss",
        "rate_limit_risk": "low_bounded_feed",             # 실측: 실 RSS smoke 429 0
        "robots_tos_status": "public_feed_bounded",
    },
    "federal_register": {
        "provider_accessibility": "key_free_rest",
        "rate_limit_risk": "low",
        "robots_tos_status": "public_api",
    },
}
_ACQUISITION_UNKNOWN: dict[str, str] = {
    "provider_accessibility": "unknown", "rate_limit_risk": "unknown",
    "robots_tos_status": "unknown_requires_legal_review",   # 신규 source 는 legal-safety review 전까지 unknown.
}


def _acquisition_profile(source_id: Optional[str]) -> dict[str, str]:
    """source_id → 운영 acquisition 제약(하드 근거만·없으면 unknown). 'rss:'/'gdelt:' prefix·정확 id 매칭."""
    sid = (source_id or "").strip()
    base = sid.split(":", 1)[0] if ":" in sid else sid
    prof = _ACQUISITION_PROFILE.get(base) or _ACQUISITION_PROFILE.get(sid)
    return dict(prof) if prof else dict(_ACQUISITION_UNKNOWN)


def _role_utilities(role: str) -> dict[str, Any]:
    return dict(_ROLE_UTILITY.get(role, _ROLE_UTILITY_UNKNOWN))


def build_source_quality_matrix(
    records: list[dict], *, failures_by_source: Optional[dict[str, str]] = None,
) -> list[dict]:
    """§9 source quality matrix(옵션 E) — source 별 body/canonical/published_at/identity readiness 진단.

    records=실 fetch(or fixture) 레코드, failures_by_source=fetch 0 인 source 의 단계별 실패.
    Agent 가 나중에 source 별 처리전략을 선택할 substrate. **본문 미포함**(수치/라벨만)."""
    failures_by_source = failures_by_source or {}
    by_source: dict[str, list[dict]] = {}
    for r in records:
        sid = r.get("source_id") or "unknown"
        by_source.setdefault(sid, []).append(r)

    rows: list[dict] = []
    for sid in sorted(by_source):
        recs = by_source[sid]
        n = len(recs)
        role = _source_type_for_record(recs[0])
        with_body = sum(1 for r in recs if (r.get("body_state_or_signal") or "missing") != "missing")
        with_canon = sum(1 for r in recs if r.get("canonical_url"))
        with_pub = sum(1 for r in recs if r.get("published_at_or_observed_at"))
        body_expected = role in _BODY_EXPECTED_SOURCE_TYPES
        anchor_eligible = role in _PUBLISHABLE_SOURCE_TYPES and with_canon > 0
        publishable = role in _PUBLISHABLE_SOURCE_TYPES
        rows.append({
            "source_id": sid,
            "source_role": role,
            "source_type": recs[0].get("record_type"),
            "fetch_ok": True,
            "records_count": n,
            "body_quality": (f"{with_body}/{n}" if body_expected
                             else ("metadata_complete" if role in _METADATA_COMPLETE_SOURCE_TYPES
                                   else "conditional")),
            "canonical_url_quality": f"{with_canon}/{n}",
            "published_at_quality": f"{with_pub}/{n}",
            "parser_status": "ok",
            # canonical/official_id 가 cross-source dedup 강신호 입력(cross_source_dedup).
            "dedup_clusterability": "strong_key_capable" if with_canon > 0 else "weak_only",
            "identity_linkability": "anchor_eligible" if anchor_eligible else "guard_only",
            "adjudication_readiness": "ready_on_cross_link" if anchor_eligible else "blocked_non_publishable",
            "packet_readiness": "needs_cross_source_link",   # 단일 bounded fetch → 동일사건 다중소스 필요
            "failure_stage": None,
            # §8 overlap potential / role utility(ADR#57) — Agent 가 source 처리전략을 선택할 substrate.
            **_role_utilities(role),
            # ADR#58 §9: source-level acquisition 제약(provider/rate-limit/robots·하드 근거만).
            **_acquisition_profile(sid),
            "agent_next_action": _agent_next_action(role, anchor_eligible),
            # §8 단계별 실패 원인(왜 anchor/adjudication/packet 이 막히는가).
            "identity_failure_reason": (None if anchor_eligible else (
                "non_publishable_role" if not publishable else "no_canonical_anchor")),
            "adjudication_failure_reason": (
                "needs_cross_batch_overlap" if anchor_eligible else (
                    "non_publishable_role" if not publishable else "no_canonical_anchor")),
            "packet_failure_reason": "needs_adjudication",
            "next_action": ("await_same_event_second_source" if anchor_eligible
                            else "keep_as_reaction_or_signal_layer"),
        })

    for sid in sorted(failures_by_source):
        if sid in by_source:
            continue   # 일부 record 가 났으면 위에서 처리됨
        stage = failures_by_source[sid]
        rows.append({
            "source_id": sid, "source_role": "unknown", "source_type": None,
            "fetch_ok": False, "records_count": 0,
            "body_quality": "n/a", "canonical_url_quality": "n/a", "published_at_quality": "n/a",
            "parser_status": stage, "dedup_clusterability": "n/a", "identity_linkability": "n/a",
            "adjudication_readiness": "n/a", "packet_readiness": "n/a",
            "failure_stage": stage,
            **_ROLE_UTILITY_UNKNOWN,
            **_acquisition_profile(sid),
            "agent_next_action": "fail_closed_investigate",
            "identity_failure_reason": stage, "adjudication_failure_reason": stage,
            "packet_failure_reason": stage,
            "next_action": _failure_next_action(stage),
        })
    return rows


def _agent_next_action(role: str, anchor_eligible: bool) -> str:
    """role → Agent 의 다음 처리 action(merge anchor 만 cross-source 수집·나머지는 layer 분리·anchor 금지)."""
    if role in _PUBLISHABLE_SOURCE_TYPES:
        return ("collect_same_event_second_source_then_adjudicate" if anchor_eligible
                else "resolve_canonical_then_recheck_anchor")
    return {
        "community": "attach_as_reaction_layer_no_anchor",
        "signal": "attach_as_market_signal_no_anchor",
        "catalog": "attach_as_entity_enrichment_no_anchor",
        "search": "resolve_url_candidate_then_route_by_role",
    }.get(role, "fail_closed_investigate")


def _failure_next_action(stage: str) -> str:
    return {
        "source_disabled": "enable_source_or_remove_from_allowlist",
        "network_error": "retry_with_backoff_or_check_egress",
        "parser_error": "inspect_payload_schema_change",
        "no_records": "widen_query_window_or_check_source_freshness",
    }.get(stage, "investigate")


# ── Agent/LLM readiness 9조건(§8·RAG_KG_AGENT_READINESS §6b) ───────────────────────────
# 시스템 상태(production backlog·gold·MERGE_GATE)로 verdict 결정. smoke 는 조건 2/3/8 의 evidence 를 실데이터로 보강.
def agent_readiness_conditions(
    smoke: dict, *, production_backlog: int = 0, has_live_gold: bool = False,
    merge_gate_passed: bool = False,
) -> list[dict]:
    """9조건 각 PASS/PARTIAL/FAIL/NOT_BUILT + evidence. 하나라도 FAIL/NOT_BUILT 면 overall No-Go."""
    role_dist = smoke.get("source_role_distribution") or {}
    non_pub = (smoke.get("failures_by_stage") or {}).get("non_publishable_role", 0)
    fp = smoke.get("semantic_fingerprint_candidates", 0)
    return [
        {"n": 1, "condition": "production/live backlog > 0",
         "status": "PASS" if production_backlog > 0 else "FAIL",
         "evidence": f"backlog={production_backlog} (test/dev smoke ≠ production)"},
        {"n": 2, "condition": "source role guard",
         "status": "PASS",
         "evidence": f"role_distribution={role_dist}·non_publishable_role 분리={non_pub} (community/market/catalog anchor 금지)"},
        {"n": 3, "condition": "semantic candidate/adjudication 존재",
         "status": "PARTIAL",
         "evidence": f"shadow adjudication 구현·smoke fingerprint_candidates={fp}; 실 cross-batch link 희소(자동병합 0)"},
        {"n": 4, "condition": "reviewer/gold 또는 eval gate",
         "status": "PASS" if has_live_gold else "FAIL",
         "evidence": "live gold 없음·현 adjudicator precision 0.57 < gate" if not has_live_gold else "live gold 존재"},
        {"n": 5, "condition": "MERGE_GATE policy 통과",
         "status": "PASS" if merge_gate_passed else "FAIL",
         "evidence": "정책 존재(precision≥0.98·FPR≤0.01·KO≥0.98)·미통과·auto_merge_enabled=False 불변"},
        {"n": 6, "condition": "raw/public output 분리",
         "status": "PARTIAL",
         "evidence": "PublicEvent 스키마 분리·IU curated synthesis 미구축(raw source 직노출 금지 코드 보존)"},
        {"n": 7, "condition": "uncertainty field 존재",
         "status": "NOT_BUILT",
         "evidence": "Event/IU uncertainty 명시 필드 미구현"},
        {"n": 8, "condition": "community reaction layer 분리",
         "status": "PASS",
         "evidence": f"non_publishable_role guard·community {role_dist.get('community', 0)} record reaction layer(anchor 아님)"},
        {"n": 9, "condition": "time-series update substrate",
         "status": "PASS",
         "evidence": "event_updates append-only·timeline 구현(S1/S2d)"},
    ]


def agent_readiness_gate(conditions: list[dict]) -> dict:
    """9조건 → overall Go/No-Go. FAIL/NOT_BUILT 가 하나라도 있으면 No-Go."""
    unmet = [c["n"] for c in conditions if c["status"] in ("FAIL", "NOT_BUILT")]
    return {"go": not unmet, "verdict": "Go" if not unmet else "No-Go", "unmet_conditions": unmet,
            "pass_count": sum(1 for c in conditions if c["status"] == "PASS"),
            "total": len(conditions)}


# ── §5 adjudication block-reason 분해(왜 adjudication=0 인가를 source/data/fingerprint 단계로) ──────────
def classify_adjudication_block_reason(smoke: dict) -> str:
    """adjudication=0 의 **정확한 원인**을 단계로 분해(순수·결정론·§5). adjudication 0 을 '실패'로 뭉뚱그리지
    않고 source scarcity / fingerprint / cross-batch / role 로 귀속한다.

    반환 값:
      - `db_not_reached`              : offline(DB 미접근·adjudications None)
      - `none`                        : adjudication 발생(차단 아님)
      - `semantic_link_without_adjudication` : semantic 후보 link 는 있으나 미판정(예: persist=False)
      - `non_publishable_role`        : 발행 가능 anchor 부재(community/market/catalog only)
      - `no_fingerprint_overlap`      : publishable 이나 fingerprint 없음(generic 제목·시점 불명 → fingerprint None)
      - `no_cross_batch_overlap`      : fingerprint 는 있으나 같은 fingerprint 의 기존 Event 부재(단일소스·distinct event)
    """
    adj = smoke.get("adjudications")
    if adj is None:
        return "db_not_reached"
    if adj > 0:
        return "none"
    semantic_links = smoke.get("semantic_cross_batch_candidates", 0) or 0
    if semantic_links > 0:
        return "semantic_link_without_adjudication"
    fp = smoke.get("semantic_fingerprint_candidates", 0) or 0
    non_pub = (smoke.get("failures_by_stage") or {}).get("non_publishable_role", 0)
    clusters = smoke.get("clusters", 0) or 0
    if fp == 0:
        if non_pub > 0 and non_pub >= clusters:
            return "non_publishable_role"
        return "no_fingerprint_overlap"
    return "no_cross_batch_overlap"


# ── §4 activation report 병합(preflight + smoke) ──────────────────────────────────────
def assemble_activation_report(
    smoke: dict, *, run_mode: str, app_env: str, database_url: str,
    failures_by_source: Optional[dict[str, str]] = None,
    records: Optional[list[dict]] = None,
    production_backlog: int = 0, has_live_gold: bool = False, merge_gate_passed: bool = False,
) -> dict:
    """smoke 결과 + db_target 분류 → 단일 activation report(§4 fields). fabrication 0·no_auto_merge 불변."""
    failures_by_source = failures_by_source or {}
    classification = classify_write_target(app_env=app_env, database_url=database_url)
    packet_eligible = smoke.get("packet_eligible")
    reviewer_packet_exportable = bool(packet_eligible) if packet_eligible is not None else None
    conditions = agent_readiness_conditions(
        smoke, production_backlog=production_backlog, has_live_gold=has_live_gold,
        merge_gate_passed=merge_gate_passed)
    matrix = build_source_quality_matrix(records or [], failures_by_source=failures_by_source)
    return {
        "run_mode": run_mode,                       # fake | live_network | live_db
        # smoke_mode: offline | single_source | time_series_replay(artificial). offline 은 DB 미도달.
        "smoke_mode": smoke.get("smoke_mode") or ("offline" if smoke.get("created_events") is None else "single_source"),
        "artificial_replay": bool(smoke.get("artificial_replay", False)),
        "batches": smoke.get("batches"),
        "db_target_classification": classification["classification"],
        "db_target_consistent": classification["consistent"],
        "is_production_target": classification["is_production_target"],
        "source_count": smoke.get("source_count"),
        "source_ids": smoke.get("source_ids"),
        "source_role_distribution": smoke.get("source_role_distribution"),
        "fetched_records": smoke.get("fetched_records"),
        "records_with_body": smoke.get("records_with_body"),
        "records_with_canonical_url": smoke.get("records_with_canonical_url"),
        "records_with_published_at": smoke.get("records_with_published_at"),
        "clusters": smoke.get("clusters"),
        "singletons_dropped": smoke.get("singletons_dropped"),
        "semantic_fingerprint_candidates": smoke.get("semantic_fingerprint_candidates"),
        # §5: 실 link reason 분포 + semantic 후보 link 수 + adjudication status 분포 + 차단 원인.
        "semantic_cross_batch_candidates": smoke.get("semantic_cross_batch_candidates"),
        "identity_link_reason_distribution": smoke.get("identity_link_reason_distribution"),
        "adjudication_status_distribution": smoke.get("adjudication_status_distribution"),
        "adjudication_block_reason": classify_adjudication_block_reason(smoke),
        "created_events": smoke.get("created_events"),
        "held_events": smoke.get("held_events"),
        "withheld_events": smoke.get("withheld_events"),
        "identity_links": smoke.get("identity_links"),
        "adjudications": smoke.get("adjudications"),
        "packet_eligible": packet_eligible,
        "packet_selected": smoke.get("packet_selected"),
        "reviewer_packet_exportable": reviewer_packet_exportable,
        "no_auto_merge": smoke.get("no_auto_merge", True),
        "event_count_before": smoke.get("event_count_before"),
        "event_count_after": smoke.get("event_count_after"),
        "failures_by_stage": smoke.get("failures_by_stage"),
        "failures_by_source": failures_by_source,
        "source_quality_matrix": matrix,
        "agent_readiness_conditions": conditions,
        "agent_readiness_gate": agent_readiness_gate(conditions),
        "next_actions": _next_actions(smoke, run_mode),
    }


def _next_actions(smoke: dict, run_mode: str) -> list[str]:
    """단계별 상태 → 다음 권장 행동(과대선언 금지·완전종결 금지)."""
    out: list[str] = []
    if run_mode == "fake":
        out.append("run --live-network for real key-free official fetch (opt-in·CI 아님)")
    if smoke.get("smoke_mode") == "time_series_replay":
        # replay 가 substrate(cross-batch→adjudication)를 닫음을 입증해도 **실 source behavior 가 아니다**.
        if (smoke.get("adjudications") or 0) > 0:
            out.append("artificial replay 가 cross-batch adjudication substrate 입증 — 다음은 **실** 동일사건 다중소스 fetch")
        out.append("artificial replay ≠ production 검증: 실 cross-source/시계열 fetch 로 재확인 필요")
    elif (smoke.get("adjudications") in (None, 0)):
        block = classify_adjudication_block_reason(smoke)
        if (smoke.get("identity_links") in (None, 0)) and smoke.get("singletons_dropped", 0) > 0:
            out.append("source scarcity: identity link 위해 동일사건 다중소스/시계열 cross-batch 필요")
        out.append(f"stage③ adjudication 0 (block={block}) — time-series replay 또는 동일사건 다중소스로 cross-batch 후보 발생 필요")
    if smoke.get("packet_eligible") in (None, 0):
        out.append("packet eligible 0 — adjudication 존재 후 reviewer export 가능")
    out.append("production 가동(운영 DB 배포·scheduler persist·gold/MERGE_GATE)은 명시적 승인 전 금지")
    return out
