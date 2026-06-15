"""Phase G-3 Final source closure runner — dcinside/culture_info/product_hunt/gdelt.

남은 비-excluded source(DEGRADED 3 + EXTERNAL_RATE_LIMITED 1)를 실데이터 기준으로 닫는다.
모든 전략은 SourceCapability → StrategyGraph → ToolPlan → EvidenceGate 흡수 구조로 흐른다.

  product_hunt : GraphQL 확장 쿼리 → 실 url/createdAt(합성 제거)         → PRODUCTION_READY
  culture_info : period2(list) → detail2(seq→실 외부 url) + startDate    → PRODUCTION_READY
  gdelt        : host rate-limit governor + spaced probe → fresh record   → READY / pending_resume
  dcinside     : robots 허용 list community_signal + detail-body audit    → preview-only DEGRADED
                 (static 본문 부재 + ToS 미검증 → 우회/browser 강행 금지)

검증된 live record만 EventQueue dedup + raw_events bridge로 적재(둔갑 금지). 외부 호출은 전부
주입형 → 단위 테스트 네트워크 0. secret 미출력. 신규 설치 0.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ingestion.orchestration.bridge_to_raw_events import RawEventBridgeWriter, bridge_records
from ingestion.orchestration.dcinside_strategy import (
    audit_dcinside_detail_body,
    collect_dcinside,
    detail_urls_from_records,
    list_url_for,
)
from ingestion.orchestration.evidence_gate import gate_records
from ingestion.orchestration.eventqueue_dedup import DedupIndex
from ingestion.orchestration.final_source_closure import (
    EXTERNAL_RATE_LIMITED_PENDING_RESUME,
    FinalSourceClosure,
    PRODUCTION_READY,
    PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY,
    classify_final_closure,
    decide_final_status,
)
from ingestion.orchestration.gdelt_strategy import collect_gdelt
from ingestion.orchestration.monitoring import build_monitoring_summary, write_monitoring_report
from ingestion.orchestration.production_scheduler import ProductionRunPlan
from ingestion.orchestration.production_state import (
    derive_production_state,
    summarize_states,
)
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.orchestration.source_capability import capability_for
from ingestion.orchestration.source_policy_probe import probe_source_policy
from ingestion.orchestration.source_profile import load_source_profiles
from ingestion.orchestration.source_strategy_memory import (
    SourceStrategyMemory,
    load_strategy_memory,
    save_strategy_memory,
)
from ingestion.orchestration.strategy_graph import build_strategy_graph
from ingestion.orchestration.vendor_api_routes import fetch_culture_info, fetch_product_hunt

_TARGETS = ("dcinside", "culture_info", "product_hunt", "gdelt")
_DC_GALLERY = "stockus"

_PROFILES = Path("ingestion/configs/source_profiles.yaml")
_MEMORY = Path("ingestion/configs/source_strategy_memory.yaml")
_QUEUE = Path("ingestion/outputs/jsonl/final_source_closure_event_queue.jsonl")
_RAW_MIRROR = Path("ingestion/outputs/raw_events/final_source_closure_raw_events_mirror.jsonl")
_DEDUP = Path("ingestion/outputs/state/eventqueue_dedup_index.json")
_GDELT_RL = Path("ingestion/outputs/state/gdelt_rate_limit_state.json")
_STATE = Path("ingestion/outputs/state/production_source_state.json")
_MONITORING = Path("ingestion/outputs/monitoring")
_OUTDIR = Path("ingestion/outputs/tmp_final_source_closure")

# dcinside DEGRADED의 load-bearing 근거는 '정책'이다(기술적 본문 추출 가능 여부가 아니라):
#  - 우리가 list-level community_signal만 수집하기로 한 정책 선택(detail 본문 미저장: 저작권/PII 보수)
#  - AI-학습 크롤러 차단 robots를 generic UA로 존중(우회 0)
#  - ToS 자동수집 미검증(legal-safety 검토 보류)
#  - 검증 범위 stockus 단일 갤러리(일반화 금지)
# detail body audit 결과(ALIVE/EMPTY/BLOCKED)는 run마다 게시글 구성에 따라 달라지므로 caveat를
# 흔들지 않고 parser_notes에 '사실'로만 기록한다(결정적 root_cause_after).
_DC_CAVEATS = ("LIST_PREVIEW_ONLY_NO_BODY_BY_POLICY",
               "AI_CRAWLER_ROBOTS_BLOCK_HONORED_GENERIC_UA", "TOS_AUTOMATED_USE_UNVERIFIED",
               "SCOPE_SINGLE_GALLERY_STOCKUS")


def _iso_now(now=None):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _graph_nodes(source_id: str) -> tuple[str, ...]:
    cap = capability_for(source_id)
    if cap is None:
        return ()
    return tuple(n.name for n in build_strategy_graph(cap).nodes)


# ── per-source closure ───────────────────────────────────────────────────────
def _close_product_hunt(*, ph_fetch) -> tuple[FinalSourceClosure, list, Optional[SourceStrategyMemory], Optional[dict]]:
    cap = capability_for("product_hunt")
    nodes = _graph_nodes("product_hunt")
    res = ph_fetch()
    records = list(res.records) if (res and res.success) else []
    gate = gate_records("product_hunt", records)
    rate_limited = bool(res and res.error == "provider_rate_limited")
    fs, reason, blocker = decide_final_status(
        capability=cap, gate=(gate if records else None), record_count=len(records),
        rate_limited=rate_limited,
        hard_blocker_evidence=(None if records or rate_limited else f"ph_fetch_failed:{res.error if res else 'none'}"))
    closure = FinalSourceClosure(
        "product_hunt", "PRODUCTION_READY_DEGRADED", nodes,
        "ph_graphql_real_url_createdAt" if fs == PRODUCTION_READY else None,
        () if records else (("ph_graphql_posts",) if res else ()),
        len(records), 0, 0, fs, reason, None, blocker, gate)
    mem = None
    patch = None
    if fs == PRODUCTION_READY:
        mem = SourceStrategyMemory(
            source_id="product_hunt", previous_status="PRODUCTION_READY_DEGRADED",
            final_status="COMMUNITY_SIGNAL_ALIVE",
            root_cause_before=("NO_STABLE_URL", "NO_TIMESTAMP"), root_cause_after=(),
            successful_strategy="ph_graphql_real_url_createdAt",
            preferred_next_strategy="ph_graphql_real_url_createdAt",
            adapter_name="vendor_route:ph_graphql_posts", parser_notes="real_url_createdAt;no_synthetic_slug",
            safety_policy="no_bypass",
            evidence=f"items={len(records)};real_url;real_createdAt;utm_stripped_canonical")
        patch = {"readiness_status": "CORE_READY", "live_eligible": "true",
                 "notes": "Phase G-3: GraphQL expanded query yields real url+createdAt (no synthetic slug)"}
    return closure, records, mem, patch


def _close_culture_info(*, culture_fetch) -> tuple[FinalSourceClosure, list, Optional[SourceStrategyMemory], Optional[dict]]:
    cap = capability_for("culture_info")
    nodes = _graph_nodes("culture_info")
    res = culture_fetch()
    records = list(res.records) if (res and res.success) else []
    gate = gate_records("culture_info", records)
    fs, reason, blocker = decide_final_status(
        capability=cap, gate=(gate if records else None), record_count=len(records),
        hard_blocker_evidence=(None if records else f"culture_fetch_failed:{res.error if res else 'none'}"))
    closure = FinalSourceClosure(
        "culture_info", "PRODUCTION_READY_DEGRADED", nodes,
        "period2_detail2_real_url" if fs == PRODUCTION_READY else None,
        () if records else (("culture_period2_detail2",) if res else ()),
        len(records), 0, 0, fs, reason, None, blocker, gate)
    mem = None
    patch = None
    if fs == PRODUCTION_READY:
        mem = SourceStrategyMemory(
            source_id="culture_info", previous_status="PRODUCTION_READY_DEGRADED",
            final_status="OFFICIAL_RECORD_ALIVE",
            root_cause_before=("NO_STABLE_URL", "NO_TIMESTAMP"), root_cause_after=(),
            successful_strategy="period2_detail2_real_url",
            preferred_next_strategy="period2_detail2_real_url",
            adapter_name="vendor_route:culture_period2_detail2",
            parser_notes="detail2_real_external_url;startDate_time_anchor", safety_policy="no_bypass",
            evidence=f"items={len(records)};detail2_real_url;startDate_anchor;seq_stable_id")
        patch = {"readiness_status": "CORE_READY", "live_eligible": "true",
                 "notes": "Phase G-3: period2->detail2 yields real external url + startDate (no dead detailView shell)"}
    return closure, records, mem, patch


def _close_gdelt(*, governor, gdelt_collect) -> tuple[FinalSourceClosure, list, Optional[SourceStrategyMemory], Optional[dict]]:
    cap = capability_for("gdelt")
    nodes = _graph_nodes("gdelt")
    res = gdelt_collect(governor)
    records = list(res.records) if (res.success and res.records) else []
    gate = gate_records("gdelt", records)
    rate_limited = (not records)   # 429/throttle/no-record → pending_resume
    fs, reason, blocker = decide_final_status(
        capability=cap, gate=(gate if records else None), record_count=len(records),
        rate_limited=rate_limited, pending_resume_at=res.next_resume_at)
    closure = FinalSourceClosure(
        "gdelt", "EXTERNAL_RATE_LIMITED", nodes,
        "host_rate_limit_spaced_probe" if fs == PRODUCTION_READY else None,
        () if records else tuple(res.attempts),
        len(records), 0, 0, fs, reason, res.next_resume_at if not records else None, blocker, gate)
    if fs == PRODUCTION_READY:
        mem = SourceStrategyMemory(
            source_id="gdelt", previous_status="EXTERNAL_RATE_LIMITED",
            final_status="OFFICIAL_RECORD_ALIVE", root_cause_before=("RATE_LIMITED",), root_cause_after=(),
            successful_strategy="host_rate_limit_spaced_probe",
            preferred_next_strategy="host_rate_limit_spaced_probe",
            cooldown_policy="respect_cooldown", safety_policy="no_bypass",
            # colab_parity는 '코드 레벨' 사실(endpoint/params/parse 동일) — test_gdelt_colab_parity로 검증.
            evidence=f"attempts={','.join(res.attempts)};items={len(records)};colab_parity_code_verified_doc2_artlist")
        patch = {"readiness_status": "CORE_READY", "live_eligible": "true"}
        return closure, records, mem, patch
    # records 0 → pending_resume(자동 재개). terminal 아님. 적대 리뷰 흡수(MEDIUM-3): 실제 사유를
    # res.error로 구분 보고(provider_429 vs no_articles)하고, colab_parity는 '코드 동일'(test-verified)로만
    # 단언(저장된 응답 diff는 없음 → 응답 레벨 parity는 UNVERIFIED로 정직 표기).
    cause = "provider_429_throttle" if res.error == "provider_rate_limited" else f"no_records:{res.error}"
    mem = SourceStrategyMemory(
        source_id="gdelt", previous_status="EXTERNAL_RATE_LIMITED",
        final_status="EXTERNAL_RATE_LIMITED_PENDING_RESUME", root_cause_before=("RATE_LIMITED",),
        root_cause_after=(cause.upper().replace(":", "_"),), successful_strategy=None,
        preferred_next_strategy="host_rate_limit_spaced_probe",
        cooldown_policy=f"respect_cooldown_until:{res.cooldown_until}", safety_policy="no_bypass",
        evidence=f"attempts={','.join(res.attempts) or 'cooldown_active'};cause={cause};"
                 f"next_resume_at={res.next_resume_at};"
                 "colab_parity:code_identical(endpoint+params+parse,test-verified);response_diff=UNVERIFIED")
    return closure, records, mem, None


def _close_dcinside(*, robots_get, dcinside_list_collect, dcinside_detail_audit) -> tuple[FinalSourceClosure, list, Optional[SourceStrategyMemory], Optional[dict]]:
    cap = capability_for("dcinside")
    nodes = _graph_nodes("dcinside")
    url = list_url_for(_DC_GALLERY, minor=True)
    probe = probe_source_policy(source_id="dcinside", tested_url=url, robots_get=robots_get)
    res = dcinside_list_collect()
    records = list(res.records) if (res.success and res.records) else []

    # 정책 차단(Cloudflare/captcha/login)이면 우회 없이 정직한 hard blocker
    if res.verdict in ("CLOUDFLARE_BLOCKED_NO_BYPASS", "CAPTCHA_BLOCKED_NO_BYPASS", "LOGIN_BLOCKED_NO_BYPASS"):
        fs, reason, blocker = decide_final_status(
            capability=cap, gate=None, record_count=0,
            hard_blocker_evidence=f"{res.verdict}:{res.blocked_reason};no_bypass")
        closure = FinalSourceClosure("dcinside", "PRODUCTION_READY_DEGRADED", nodes, None,
                                     (res.verdict,), 0, 0, 0, fs, reason, None, blocker, None)
        return closure, [], None, None

    # detail body audit (우회/browser 강행 없음) — 기술적 본문 추출 가능성을 '사실'로만 기록.
    # 결과와 무관하게 dcinside는 정책 근거(_DC_CAVEATS)로 preview-only DEGRADED 유지(보수).
    detail_urls = detail_urls_from_records(records)
    audit = dcinside_detail_audit(detail_urls)
    gate = gate_records("dcinside", records)
    fs, reason, blocker = decide_final_status(
        capability=cap, gate=(gate if records else None), record_count=len(records),
        caveats=_DC_CAVEATS,
        hard_blocker_evidence=(None if records else f"{res.verdict}:{res.blocked_reason}"))
    closure = FinalSourceClosure(
        "dcinside", "PRODUCTION_READY_DEGRADED", nodes,
        "robots_allowed_static_list_fetch" if records else None,
        () if records else (res.verdict,),
        len(records), 0, 0, fs, reason, None, blocker, gate)
    if not records:
        return closure, [], None, None
    mem = SourceStrategyMemory(
        source_id="dcinside", previous_status="PRODUCTION_READY_DEGRADED",
        final_status="COMMUNITY_SIGNAL_ALIVE",
        root_cause_before=("ROBOTS_OR_POLICY_BLOCK_OVERCAUTIOUS",), root_cause_after=_DC_CAVEATS,
        successful_strategy="robots_allowed_static_list_fetch",
        preferred_next_strategy="robots_allowed_static_list_fetch",
        parser_notes=(f"dcinside_list_community_signal;no_pii_nickname;list_meta_only;"
                      f"detail_audit={audit.conclusion}(best_body_chars={audit.best_body_chars})"),
        cooldown_policy="respect_min_interval", safety_policy="no_bypass",
        evidence=(f"gallery={_DC_GALLERY}_only;items={len(records)};robots_user_agent_star_allow;"
                  f"ai_training_crawler_block_honored_via_generic_ua;tos_automated_use_unverified;"
                  f"detail_body_static={audit.conclusion};no_bypass"))
    patch = {"readiness_status": "DEGRADED_PREVIEW_ONLY", "live_eligible": "true",
             "notes": "Phase G-3: stockus list community_signal only; detail body empty in static "
                      "(JS/image render) — no browser bypass; ToS automated-use UNVERIFIED (legal review pending)"}
    return closure, records, mem, patch


# ── main ─────────────────────────────────────────────────────────────────────
def run_final_source_closure(
    *,
    profiles_path: Path = _PROFILES,
    memory_path: Path = _MEMORY,
    queue_path: Path = _QUEUE,
    raw_mirror_path: Path = _RAW_MIRROR,
    dedup_index_path: Path = _DEDUP,
    gdelt_rl_path: Path = _GDELT_RL,
    state_path: Path = _STATE,
    monitoring_dir: Path = _MONITORING,
    output_dir: Path = _OUTDIR,
    robots_get: Optional[Callable] = None,
    dcinside_list_collect: Optional[Callable] = None,
    dcinside_detail_audit: Optional[Callable] = None,
    ph_fetch: Optional[Callable] = None,
    culture_fetch: Optional[Callable] = None,
    gdelt_collect: Optional[Callable] = None,
    gdelt_min_interval_seconds: int = 10,
    gdelt_max_probes: int = 3,
    apply_config: bool = True,
    write_outputs: bool = True,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    run_id = run_id or _iso_now(now).replace(":", "").replace("-", "")

    # 주입 기본값(실 네트워크)
    if robots_get is None:
        robots_get = _default_robots_get
    if dcinside_list_collect is None:
        dcinside_list_collect = lambda: collect_dcinside(gallery_id=_DC_GALLERY, minor=True, robots_allowed=True)
    if dcinside_detail_audit is None:
        dcinside_detail_audit = lambda urls: audit_dcinside_detail_body(detail_urls=urls)
    if ph_fetch is None:
        ph_fetch = lambda: fetch_product_hunt(limit=5)
    if culture_fetch is None:
        culture_fetch = lambda: fetch_culture_info(limit=5, now=now)
    if gdelt_collect is None:
        def gdelt_collect(gov):
            return collect_gdelt(governor=gov, min_interval_seconds=gdelt_min_interval_seconds,
                                 max_probes=gdelt_max_probes, now=now, sleep=time.sleep)

    governor = RateLimitGovernor(state_path=(gdelt_rl_path if write_outputs else None))

    results: list[FinalSourceClosure] = []
    eq_records: list[dict] = []
    memory_updates: list[SourceStrategyMemory] = []
    profile_patches: dict = {}

    for builder in (
        lambda: _close_dcinside(robots_get=robots_get, dcinside_list_collect=dcinside_list_collect,
                                dcinside_detail_audit=dcinside_detail_audit),
        lambda: _close_culture_info(culture_fetch=culture_fetch),
        lambda: _close_product_hunt(ph_fetch=ph_fetch),
        lambda: _close_gdelt(governor=governor, gdelt_collect=gdelt_collect),
    ):
        closure, recs, mem, patch = builder()
        results.append(closure)
        if recs:
            eq_records.extend(recs)
        if mem is not None:
            memory_updates.append(mem)
        if patch is not None:
            profile_patches[closure.source_id] = patch

    # EventQueue dedup + raw_events bridge (검증된 live record만)
    dedup_index = DedupIndex(path=dedup_index_path if write_outputs else None)
    written: list[dict] = []
    duplicates = 0
    for i, rec in enumerate(eq_records):
        d = dedup_index.decide(rec, ref=f"{run_id}:{i}")
        if d.is_duplicate:
            duplicates += 1
            continue
        rec = dict(rec); rec["_dedup_key"] = d.record_key
        written.append(rec)
    if write_outputs and written:
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        with open(queue_path, "a", encoding="utf-8") as f:
            for rec in written:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    writer = RawEventBridgeWriter(mirror_path=(raw_mirror_path if write_outputs else None))
    bridge_result = bridge_records(written, writer=writer, collected_at=_iso_now(now))

    raw_by_source: dict = {}
    for rec in written:
        raw_by_source[rec["source_id"]] = raw_by_source.get(rec["source_id"], 0) + 1
    results = [_with_counts(r, raw_by_source.get(r.source_id, 0)) for r in results]

    # canonical memory 갱신(기존 entries 보존 병합)
    memory_written = 0
    merged: dict = {}
    if memory_updates or apply_config:
        existing = load_strategy_memory(memory_path)
        merged = dict(existing)
        for m in memory_updates:
            merged[m.source_id] = m
        if apply_config and memory_updates:
            save_strategy_memory(list(merged.values()), memory_path, run_id=run_id)
            memory_written = len(memory_updates)

    if write_outputs:
        governor.save()

    verdict = classify_final_closure(results)

    # production_state 재산출(분포/degraded_remaining 확인)
    state_summary = _recompute_states(profiles_path, merged or load_strategy_memory(memory_path))

    # monitoring
    plan = ProductionRunPlan(
        run_id=run_id, created_at=_iso_now(now), due_sources=_TARGETS, skipped_sources=(),
        skipped_reasons={}, expected_calls=len(_TARGETS), strategy_by_source={},
        mode="final-source-closure", skip_category_counts={})
    rtc: dict = {}
    for rec in written:
        rtc[rec["record_type"]] = rtc.get(rec["record_type"], 0) + 1
    summary = build_monitoring_summary(
        run_id=run_id, plan=plan, source_states=[], records_collected=len(eq_records),
        eventqueue_written=len(written), duplicates_skipped=duplicates, bridge_result=bridge_result,
        record_type_counts=rtc, queue_or_raw_sample=written)
    summary["verdict"] = verdict["verdict"]
    summary["degraded_remaining"] = verdict["degraded_remaining"]
    summary["external_rate_limited_remaining"] = verdict["external_rate_limited_remaining"]

    monitoring_paths = {}
    if write_outputs:
        out = output_dir / run_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "final_source_closure_result.json").write_text(
            json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=1), encoding="utf-8")
        monitoring_paths = write_monitoring_report(summary, [], monitoring_dir=monitoring_dir, run_id=run_id)
        dedup_index.save()

    return {
        "run_id": run_id, "results": results, "verdict": verdict,
        "eventqueue_written": len(written), "duplicates_skipped": duplicates,
        "raw_events_written": bridge_result.get("raw_events_written", 0),
        "bridge_contract_pass": bridge_result.get("bridge_contract_pass", False),
        "raw_by_source": raw_by_source, "memory_written": memory_written,
        "profile_patches": profile_patches, "critical_alerts": summary["critical_alert_count"],
        "state_summary": state_summary, "monitoring_paths": monitoring_paths, "summary": summary,
    }


def _with_counts(r: FinalSourceClosure, raw_n: int) -> FinalSourceClosure:
    from dataclasses import replace
    eq_n = raw_n if r.live_records else 0
    if r.eventqueue_records == eq_n and r.raw_events_records == raw_n:
        return r
    return replace(r, eventqueue_records=eq_n, raw_events_records=raw_n)


def _recompute_states(profiles_path, memory: dict) -> dict:
    """profiles + 갱신된 memory → production_state 분포 요약(degraded_remaining 등).

    canonical readiness closure와 동일하게 api_key_ready(env 키 존재 여부)를 반영한다 —
    그래야 key 보유 source가 거짓으로 not-ready로 집계되지 않는다.
    """
    try:
        profiles = load_source_profiles(str(profiles_path))
    except Exception as exc:
        return {"error": f"load_profiles_failed:{type(exc).__name__}"}
    try:
        from ingestion.orchestration.api_readiness import audit_api_key_readiness
        rd = {r.source_id: bool(getattr(r, "keys_present", False))
              for r in audit_api_key_readiness(profiles, env_path=None)}
    except Exception:
        rd = {}
    states = [derive_production_state(p, memory=memory, api_key_ready=rd.get(p.source_id, False))
              for p in profiles]
    summ = summarize_states(states)
    dist = summ["distribution"]
    summ["degraded_remaining"] = dist.get("PRODUCTION_READY_DEGRADED", 0)
    summ["external_rate_limited_remaining"] = dist.get("EXTERNAL_RATE_LIMITED", 0)
    # canonical readiness closure와 동일 정의: clean READY와 POLICY_EXCLUDED 외 전부(=degraded 포함).
    summ["non_excluded_not_ready"] = sum(
        v for k, v in dist.items()
        if k not in ("PRODUCTION_READY", "POLICY_EXCLUDED"))
    return summ


def _default_robots_get(robots_url: str) -> Optional[str]:
    try:
        import httpx
        resp = httpx.get(robots_url, timeout=15.0, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; eventintel-collector/1.0)"})
        return resp.text if resp.status_code == 200 else None
    except Exception:
        return None


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Phase G-3 final source closure")
    ap.add_argument("--sources", default=",".join(_TARGETS))
    ap.add_argument("--no-apply", action="store_true")
    ap.add_argument("--no-outputs", action="store_true")
    ap.add_argument("--gdelt-min-interval-seconds", type=int, default=10)
    ap.add_argument("--max-policy-compliant-probes-per-source", type=int, default=3)
    args = ap.parse_args(argv)

    print("FINAL_SOURCE_CLOSURE_PLAN:")
    print(f"- target_sources: {list(_TARGETS)}")
    print("- current_status: dcinside/culture_info/product_hunt=DEGRADED, gdelt=EXTERNAL_RATE_LIMITED")
    print("- source_capabilities: SourceCapability(list/detail/api/static/browser/key/rate_limit/policy)")
    print("- policy_probe_required: dcinside(robots)")
    print("- strategy_graphs: capability -> StrategyGraph -> ToolPlan -> EvidenceGate")
    print("- gdelt_colab_parity_audit_required: True (endpoint/params/parse vs Colab DOC2.0 ArtList)")
    print(f"- max_policy_compliant_probes: gdelt={args.max_policy_compliant_probes_per_source}")
    print("- no_bypass: True (robots-allowed only; respect cooldown; no browser/proxy/captcha bypass)")

    result = run_final_source_closure(
        apply_config=not args.no_apply, write_outputs=not args.no_outputs,
        gdelt_min_interval_seconds=args.gdelt_min_interval_seconds,
        gdelt_max_probes=args.max_policy_compliant_probes_per_source)

    print("\nFINAL_SOURCE_CLOSURE_RESULT:")
    print(f"- verdict: {result['verdict']['verdict']}")
    for r in result["results"]:
        print(f"- {r.source_id}: final_status={r.final_status} live={r.live_records} "
              f"eq={r.eventqueue_records} raw={r.raw_events_records} "
              f"resume_at={r.pending_resume_at or '-'} strategy={r.successful_strategy or '-'}")
    print(f"- eventqueue_records: {result['eventqueue_written']} (dup_skipped={result['duplicates_skipped']})")
    print(f"- raw_events_records: {result['raw_events_written']} contract_pass={result['bridge_contract_pass']}")
    print(f"- degraded_remaining: {result['verdict']['degraded_remaining']}")
    print(f"- rate_limited_remaining: {result['verdict']['external_rate_limited_remaining']}")
    ss = result.get("state_summary", {})
    print(f"- production_state: ready={ss.get('production_ready')} "
          f"non_excluded_not_ready={ss.get('non_excluded_not_ready')} unknown={ss.get('unknown')}")
    print(f"- critical_alerts: {result['critical_alerts']}")
    return 1 if result["critical_alerts"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
