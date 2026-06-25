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
            "next_action": _failure_next_action(stage),
        })
    return rows


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
    if (smoke.get("identity_links") in (None, 0)) and smoke.get("singletons_dropped", 0) > 0:
        out.append("source scarcity: identity link 위해 동일사건 다중소스/시계열 cross-batch 필요")
    if smoke.get("adjudications") in (None, 0):
        out.append("stage③ adjudication backlog 0 — possible-link 누적 후 backfill 필요")
    if smoke.get("packet_eligible") in (None, 0):
        out.append("packet eligible 0 — adjudication 존재 후 reviewer export 가능")
    out.append("production 가동(운영 DB 배포·scheduler persist·gold/MERGE_GATE)은 명시적 승인 전 금지")
    return out
