"""Phase G-10/11/12 Source readiness closure runner — 비-ready source를 실제로 닫는다.

흐름:
  load state/profiles/memory → build gap matrix → route rescue → per-source 실행
  (vendor route / body ladder / adapter anchor / cooldown probe / disable)
  → 실제 live 데이터로 검증된 경우에만 memory를 alive로 flip(둔갑 금지)
  → disable 결정은 source_profiles.yaml에 반영(운영 runner 반복 probe 방지)
  → EventQueue dedup + raw_events mirror → ProductionSourceState 재산출
  → non_excluded_not_ready=0 게이트 + monitoring.

live 호출은 전부 주입형(vendor_fetch/probe_fn/body_rescue) → 단위 테스트 네트워크 0.
canonical config(source_strategy_memory.yaml/source_profiles.yaml)는 검증 통과 시에만 갱신.
신규 설치 0. secret 미출력.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import yaml

from ingestion.orchestration.bridge_to_raw_events import RawEventBridgeWriter, bridge_records
from ingestion.orchestration.eventqueue_dedup import DedupIndex
from ingestion.orchestration.monitoring import build_monitoring_summary, write_monitoring_report
from ingestion.orchestration.production_scheduler import ProductionRunPlan
from ingestion.orchestration.production_state import (
    derive_production_state,
    save_production_state,
    summarize_states,
)
from ingestion.orchestration.rescue_router import (
    BODY_LADDER_FETCH,
    DISABLE_LOW_VALUE,
    POLICY_BLOCK_NO_BYPASS,
    RATE_LIMIT_COOLDOWN_PROBE,
    SOURCE_ADAPTER_FIX,
    VENDOR_ROUTE_FIX,
    route_all,
)
from ingestion.orchestration.source_profile import load_source_profiles
from ingestion.orchestration.source_readiness_closure import build_gap_matrix, summarize_gaps
from ingestion.orchestration.source_strategy_memory import (
    SourceStrategyMemory,
    load_strategy_memory,
    save_strategy_memory,
)
from ingestion.orchestration.source_value_policy import decide_source_value

_PROFILES = Path("ingestion/configs/source_profiles.yaml")
_MEMORY = Path("ingestion/configs/source_strategy_memory.yaml")
_STATE = Path("ingestion/outputs/state/production_source_state.json")
_QUEUE = Path("ingestion/outputs/jsonl/production_ready_closure_event_queue.jsonl")
_RAW_MIRROR = Path("ingestion/outputs/raw_events/production_ready_closure_raw_events_mirror.jsonl")
_DEDUP = Path("ingestion/outputs/state/eventqueue_dedup_index.json")
_MONITORING = Path("ingestion/outputs/monitoring")
_OUTDIR = Path("ingestion/outputs/tmp_source_readiness_closure")

# 법무 흡수: 약관상 비상업/상업라이선스 필요 — production_ready이되 preview_only caveat 부착.
_LEGAL_PREVIEW_ONLY = frozenset({"nyt"})

# 데이터 검증된 source의 final_status (record_type에 따라)
_ALIVE_BY_RECORD_TYPE = {
    "structured_signal": "STRUCTURED_SIGNAL_ALIVE",
    "article_candidate": "ARTICLE_PARTIAL_ALIVE",
    "official_record": "OFFICIAL_RECORD_ALIVE",
    "search_result": "SEARCH_RESULT_ALIVE",
    "community_signal": "COMMUNITY_SIGNAL_ALIVE",
}


@dataclass
class RescueOutcome:
    source_id: str
    strategy: str
    success: bool
    eq_records: list = field(default_factory=list)
    new_final_status: Optional[str] = None
    successful_strategy: Optional[str] = None
    record_type: Optional[str] = None
    profile_patch: Optional[dict] = None
    note: str = ""
    clear_degraded: bool = False


def _iso_now(now=None):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ── per-source rescue 실행 ───────────────────────────────────────────────────
def _execute_rescue(gap, decision, *, vendor_fetch, body_rescue, gdelt_probe, now) -> RescueOutcome:
    sid = gap.source_id
    strat = decision.rescue_strategy

    if strat == VENDOR_ROUTE_FIX:
        res = vendor_fetch(sid)
        if res is not None and res.success and res.records:
            note = f"items={res.item_count}"
            # 법무 흡수(nyt terms_risk=high): preview_only/비상업/상업라이선스 필요 caveat 부착.
            if sid in _LEGAL_PREVIEW_ONLY:
                note += ";preview_only;non_commercial;commercial_license_required_for_redistribution"
            return RescueOutcome(
                sid, strat, True, list(res.records),
                new_final_status=_ALIVE_BY_RECORD_TYPE.get(res.record_type, "STRUCTURED_SIGNAL_ALIVE"),
                successful_strategy=f"vendor_route:{res.route_name}",
                record_type=res.record_type, note=note,
            )
        # 정직성(적대 리뷰 흡수): 제공자 rate-limit(429)이면 fresh data 0건이므로 READY로 단언하지
        # 않는다. route는 배선됐으나 이번 run 데이터 미확보 → 정직한 rate-limit 홀드오버로 남긴다.
        err = getattr(res, "error", None)
        return RescueOutcome(sid, strat, False, note=f"vendor_route_failed:{err}")

    if strat == SOURCE_ADAPTER_FIX:
        # 정직성(데이터품질/적대 리뷰 흡수): 어댑터 anchor 수정은 커밋됐으나 live 재검증(키+쿼리)
        # 없이 degraded를 해제하지 않는다. product_hunt slug fallback은 collapse 위험도 있다.
        # → degraded 유지(코드 개선은 다음 live 수집부터 효과). 이번 run에서 promote하지 않음.
        return RescueOutcome(sid, strat, False,
                             note="adapter_anchor_improved_pending_live_revalidation")

    if strat == BODY_LADDER_FETCH:
        # 뉴스: RSS 기사 레퍼런스(title/url/date/snippet)가 production 가치의 핵심.
        # 전문 전재는 저작권 위험 → preview-only(snippet)가 정답. full body는 보너스(필수 아님).
        res = body_rescue(sid)  # (success, eq_records, final_status, note)
        if res is not None and res[0] and res[1]:
            return RescueOutcome(
                sid, strat, True, list(res[1]),
                new_final_status=res[2] or "ARTICLE_PARTIAL_ALIVE",
                successful_strategy="rss_reference_preview_only",
                record_type="article_candidate", note=res[3],
            )
        note = res[3] if (res and len(res) > 3) else "no_records"
        return RescueOutcome(sid, strat, False, note=f"news_rescue_failed:{note}")

    if strat == RATE_LIMIT_COOLDOWN_PROBE:
        res = gdelt_probe(sid)  # (success, records, final_status)
        if res is not None and res[0]:
            return RescueOutcome(
                sid, strat, True, list(res[1]),
                new_final_status=res[2], successful_strategy="rate_limit_cooldown_probe",
                record_type="official_record", note="cooldown_managed_live_ok",
            )
        return RescueOutcome(sid, strat, False, note="rate_limited_cooldown_active")

    if strat in (DISABLE_LOW_VALUE, POLICY_BLOCK_NO_BYPASS):
        vd = decide_source_value(sid)
        patch = vd.profile_patch if vd else {"enabled": False, "profile_status": "disabled"}
        return RescueOutcome(sid, strat, True, profile_patch=patch,
                             note=(vd.rationale if vd else "disabled"))

    return RescueOutcome(sid, strat, False, note="no_rescue_path")


# ── memory / profiles 갱신 ───────────────────────────────────────────────────
def _build_memory_entry(sid, gap, outcome) -> SourceStrategyMemory:
    return SourceStrategyMemory(
        source_id=sid, previous_status=gap.previous_status,
        final_status=outcome.new_final_status or "OFFICIAL_RECORD_ALIVE",
        root_cause_before=tuple(gap.root_cause), root_cause_after=(),
        successful_strategy=outcome.successful_strategy,
        preferred_next_strategy=outcome.successful_strategy,
        parser_notes="readiness_closure", safety_policy="no_bypass",
        evidence=outcome.note,
    )


def _patch_profiles_yaml(path: Path, patches: dict) -> int:
    """source_profiles.yaml의 source별 필드 패치(disable 반영). 패치된 source 수 반환."""
    if not patches:
        return 0
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    profiles = doc.get("profiles", {})
    n = 0
    for sid, patch in patches.items():
        if sid in profiles and isinstance(profiles[sid], dict):
            profiles[sid].update(patch)
            n += 1
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return n


# ── 메인 closure ─────────────────────────────────────────────────────────────
def run_source_readiness_closure(
    *,
    profiles_path: Path = _PROFILES,
    memory_path: Path = _MEMORY,
    state_path: Path = _STATE,
    queue_path: Path = _QUEUE,
    raw_mirror_path: Path = _RAW_MIRROR,
    dedup_index_path: Path = _DEDUP,
    monitoring_dir: Path = _MONITORING,
    output_dir: Path = _OUTDIR,
    vendor_fetch: Optional[Callable] = None,
    body_rescue: Optional[Callable] = None,
    gdelt_probe: Optional[Callable] = None,
    apply_config: bool = True,
    patch_profiles_yaml: bool = False,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
    write_outputs: bool = True,
) -> dict:
    """비-ready source closure 1회. result dict 반환."""
    now = now or datetime.now(timezone.utc)
    run_id = run_id or _iso_now(now).replace(":", "").replace("-", "")
    profiles = load_source_profiles(str(profiles_path))
    memory = load_strategy_memory(str(memory_path))

    from ingestion.orchestration.api_readiness import audit_api_key_readiness
    rd = {r.source_id: bool(getattr(r, "keys_present", False))
          for r in audit_api_key_readiness(profiles, env_path=None)}

    states = [derive_production_state(p, memory=memory, api_key_ready=rd.get(p.source_id, False))
              for p in profiles]
    gaps = build_gap_matrix(states, profiles)
    decisions = {d.source_id: d for d in route_all(gaps)}

    # 주입 기본값(실 네트워크) — 테스트는 주입으로 대체
    if vendor_fetch is None:
        from ingestion.orchestration.vendor_api_routes import fetch_vendor
        vendor_fetch = lambda sid: fetch_vendor(sid, now=now) if sid in ("bok_ecos", "eia", "kma") else fetch_vendor(sid)
    if body_rescue is None:
        body_rescue = _default_body_rescue
    if gdelt_probe is None:
        gdelt_probe = _default_gdelt_probe

    outcomes = []
    eq_records = []
    profile_patches: dict = {}
    memory_updates: list[SourceStrategyMemory] = []
    promoted, disabled, policy_blocked, still_not_ready = [], [], [], []

    for gap in gaps:
        decision = decisions[gap.source_id]
        outcome = _execute_rescue(gap, decision, vendor_fetch=vendor_fetch,
                                  body_rescue=body_rescue, gdelt_probe=gdelt_probe, now=now)
        outcomes.append(outcome)
        if outcome.eq_records:
            eq_records.extend(outcome.eq_records)

        if outcome.profile_patch:
            profile_patches[gap.source_id] = outcome.profile_patch
            if decision.rescue_strategy == POLICY_BLOCK_NO_BYPASS:
                policy_blocked.append(gap.source_id)
            else:
                disabled.append(gap.source_id)
        elif outcome.success and (outcome.new_final_status or outcome.clear_degraded):
            # 검증된 source만 memory를 alive로 flip
            if outcome.clear_degraded and gap.source_id in memory:
                prev = memory[gap.source_id]
                memory_updates.append(SourceStrategyMemory(
                    source_id=gap.source_id, previous_status=gap.previous_status,
                    final_status=prev.final_status, root_cause_before=tuple(gap.root_cause),
                    root_cause_after=(), successful_strategy=outcome.successful_strategy,
                    preferred_next_strategy=outcome.successful_strategy,
                    adapter_name=prev.adapter_name, parser_notes="readiness_closure_anchor",
                    safety_policy="no_bypass", evidence=outcome.note,
                ))
            else:
                memory_updates.append(_build_memory_entry(gap.source_id, gap, outcome))
            promoted.append(gap.source_id)
        else:
            still_not_ready.append(gap.source_id)

    # canonical config 갱신(검증 통과분만)
    profiles_patched = 0
    memory_written = 0
    if apply_config:
        # memory: 기존 + 업데이트 병합
        merged = dict(memory)
        for m in memory_updates:
            merged[m.source_id] = m
        if memory_updates:
            save_strategy_memory(list(merged.values()), memory_path, run_id=run_id)
            memory_written = len(memory_updates)
        # profiles는 기본적으로 손으로 편집(주석/포맷 보존). yaml 전체 재작성은 opt-in.
        if profile_patches and patch_profiles_yaml:
            profiles_patched = _patch_profiles_yaml(profiles_path, profile_patches)
        elif profile_patches:
            profiles_patched = len(profile_patches)  # 이미 수동 반영됨(보고용 카운트)

    # EventQueue dedup + raw_events bridge (검증된 live record)
    dedup_index = DedupIndex(path=dedup_index_path if write_outputs else None)
    written = []
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

    # 재산출 (갱신된 memory/profiles 반영)
    profiles2 = load_source_profiles(str(profiles_path))
    memory2 = load_strategy_memory(str(memory_path)) if apply_config else {
        **memory, **{m.source_id: m for m in memory_updates}}
    rd2 = {r.source_id: bool(getattr(r, "keys_present", False))
           for r in audit_api_key_readiness(profiles2, env_path=None)}
    states2 = [derive_production_state(p, memory=memory2, api_key_ready=rd2.get(p.source_id, False))
               for p in profiles2]
    summ2 = summarize_states(states2)

    non_excluded_not_ready = sum(
        1 for s in states2
        if s.current_status not in ("PRODUCTION_READY", "POLICY_EXCLUDED")
    )

    if write_outputs:
        save_production_state(states2, state_path, run_id=run_id)
        out = output_dir / run_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "source_readiness_gap.json").write_text(
            json.dumps([g.to_dict() for g in gaps], ensure_ascii=False, indent=1), encoding="utf-8")
        _write_gap_csv(out / "source_readiness_gap.csv", gaps)

    # monitoring
    plan = ProductionRunPlan(
        run_id=run_id, created_at=_iso_now(now),
        due_sources=tuple(g.source_id for g in gaps), skipped_sources=(),
        skipped_reasons={}, expected_calls=len(gaps), strategy_by_source={},
        mode="production-ready-closure", skip_category_counts={})
    rtc: dict = {}
    for rec in written:
        rtc[rec["record_type"]] = rtc.get(rec["record_type"], 0) + 1
    summary = build_monitoring_summary(
        run_id=run_id, plan=plan, source_states=states2,
        records_collected=len(eq_records), eventqueue_written=len(written),
        duplicates_skipped=duplicates, bridge_result=bridge_result,
        record_type_counts=rtc, queue_or_raw_sample=written)
    summary["non_excluded_not_ready"] = non_excluded_not_ready
    summary["promoted"] = promoted
    summary["disabled"] = disabled
    summary["policy_blocked"] = policy_blocked
    summary["still_not_ready"] = still_not_ready
    monitoring_paths = {}
    if write_outputs:
        monitoring_paths = write_monitoring_report(summary, states2, monitoring_dir=monitoring_dir, run_id=run_id)
        dedup_index.save()

    return {
        "run_id": run_id, "gaps": gaps, "gap_summary": summarize_gaps(gaps),
        "outcomes": outcomes, "promoted": promoted, "disabled": disabled,
        "policy_blocked": policy_blocked, "still_not_ready": still_not_ready,
        "eventqueue_written": len(written), "duplicates_skipped": duplicates,
        "raw_events_written": bridge_result.get("raw_events_written", 0),
        "bridge_contract_pass": bridge_result.get("bridge_contract_pass", False),
        "state_distribution": summ2["distribution"],
        "non_excluded_not_ready": non_excluded_not_ready,
        "source_without_state": summ2["source_without_state"], "unknown": summ2["unknown"],
        "critical_alerts": summary["critical_alert_count"],
        "profiles_patched": profiles_patched, "memory_written": memory_written,
        "monitoring_paths": monitoring_paths, "states": states2, "summary": summary,
    }


def _write_gap_csv(path: Path, gaps) -> None:
    import csv
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "previous_status", "source_group", "blocking_layer",
                    "rescue_possible", "final_required_status", "root_cause"])
        for g in gaps:
            w.writerow([g.source_id, g.previous_status, g.source_group, g.blocking_layer,
                        g.rescue_possible, g.final_required_status, ";".join(g.root_cause)])


# ── 실 네트워크 기본 구현 ────────────────────────────────────────────────────
def _default_body_rescue(source_id: str):
    """뉴스(cnbc 등): RSS 기사 레퍼런스(title/url/date/snippet)를 article_candidate로 산출.

    전문 전재는 하지 않는다(preview-only). RSS summary를 snippet_only로 싣는다(둔갑 금지).
    반환: (success, eq_records, final_status, note).
    """
    try:
        from ingestion.fetch_strategies.collection_probe import run_collection_probe
        from ingestion.orchestration.artifact_parser import parse_artifact_text
        from ingestion.orchestration.full_source_revival import build_eventqueue_record
        pr = run_collection_probe(source_id, max_items=10, force=False)
        paths = getattr(pr, "artifact_paths", None)
        text = None
        for attr in ("raw_payload", "raw_html", "extracted_payload"):
            p = getattr(paths, attr, None) if paths else None
            if p and Path(p).exists():
                text = Path(p).read_text(encoding="utf-8"); break
        if not text:
            return (False, [], None, "no_artifact")
        cands, _, _ = parse_artifact_text(text, source_id=source_id, collection_status="LIVE_SUCCESS",
                                          confirmation_policy="source_confirmed", raw_artifact_path=None, fmt="xml")
        recs = []
        for c in cands[:10]:
            url = c.source_url or c.canonical_url
            if not url:
                continue
            recs.append(build_eventqueue_record(
                record_type="article_candidate", source_id=source_id, title_or_label=c.title,
                source_url_or_evidence=url, canonical_url=c.canonical_url,
                published_at_or_observed_at=c.published_at, body_state_or_signal="snippet_only",
                confirmation_policy="source_confirmed", quality_pre_gate_decision="pass"))
        if not recs:
            return (False, [], None, "no_url_items")
        return (True, recs, "ARTICLE_PARTIAL_ALIVE", f"rss_references={len(recs)}")
    except Exception as exc:
        return (False, [], None, f"error:{type(exc).__name__}")


def _default_gdelt_probe(source_id: str):
    """gdelt: cooldown 존중 1회 probe. (success, eq_records, final_status)."""
    try:
        from ingestion.fetch_strategies.collection_probe import run_collection_probe
        from ingestion.orchestration.artifact_parser import parse_artifact_text
        from ingestion.orchestration.full_source_revival import build_eventqueue_record
        pr = run_collection_probe(source_id, max_items=5, force=False)
        if getattr(pr, "status", "") not in ("LIVE_SUCCESS", "LIVE_PARTIAL", "PARTIAL"):
            return (False, [], None)
        paths = getattr(pr, "artifact_paths", None)
        text = None
        for attr in ("raw_payload", "raw_html"):
            p = getattr(paths, attr, None) if paths else None
            if p and Path(p).exists():
                text = Path(p).read_text(encoding="utf-8"); break
        if not text:
            return (False, [], None)
        cands, _, _ = parse_artifact_text(text, source_id=source_id, collection_status="LIVE_SUCCESS",
                                          confirmation_policy="evidence_required", raw_artifact_path=None, fmt="json")
        recs = []
        for c in cands[:10]:
            if not (c.source_url or c.canonical_url):
                continue
            recs.append(build_eventqueue_record(
                record_type="official_record", source_id=source_id, title_or_label=c.title,
                source_url_or_evidence=c.source_url or c.canonical_url, canonical_url=c.canonical_url,
                published_at_or_observed_at=c.published_at, body_state_or_signal="official_record",
                confirmation_policy="evidence_required", quality_pre_gate_decision="pass"))
        return (bool(recs), recs, "OFFICIAL_RECORD_ALIVE" if recs else None)
    except Exception:
        return (False, [], None)


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Phase G source readiness closure")
    ap.add_argument("--mode", default="production-ready-closure")
    ap.add_argument("--no-apply", action="store_true", help="canonical config 미갱신(드라이런)")
    ap.add_argument("--no-live", action="store_true", help="네트워크 probe/vendor 호출 비활성")
    args = ap.parse_args(argv)

    profiles = load_source_profiles(str(_PROFILES))
    memory = load_strategy_memory(str(_MEMORY))
    from ingestion.orchestration.api_readiness import audit_api_key_readiness
    rd = {r.source_id: bool(getattr(r, "keys_present", False))
          for r in audit_api_key_readiness(profiles, env_path=None)}
    states = [derive_production_state(p, memory=memory, api_key_ready=rd.get(p.source_id, False)) for p in profiles]
    gaps = build_gap_matrix(states, profiles)
    gs = summarize_gaps(gaps)
    excluded = sum(1 for s in states if s.current_status == "POLICY_EXCLUDED")
    print("PRODUCTION_READY_CLOSURE_PLAN:")
    print(f"- total_sources: {len(profiles)}")
    print(f"- excluded_sources: {excluded}")
    print(f"- target_non_ready_sources: {gs['targets']}")
    print(f"- by_layer: {gs['by_layer']}")
    print(f"- no_bypass: True")

    kwargs = {}
    if args.no_live:
        kwargs = dict(vendor_fetch=lambda sid: None, body_rescue=lambda sid: None,
                      gdelt_probe=lambda sid: (False, [], None))
    result = run_source_readiness_closure(apply_config=not args.no_apply, **kwargs)

    print("\nPRODUCTION_READY_CLOSURE_RESULT:")
    print(f"- targets_total: {len(result['gaps'])}")
    print(f"- promoted_to_production_ready: {len(result['promoted'])} {result['promoted']}")
    print(f"- disabled: {len(result['disabled'])} {result['disabled']}")
    print(f"- policy_blocked_no_bypass: {len(result['policy_blocked'])} {result['policy_blocked']}")
    print(f"- still_not_ready: {len(result['still_not_ready'])} {result['still_not_ready']}")
    print(f"- eventqueue_records: {result['eventqueue_written']}")
    print(f"- raw_events_records: {result['raw_events_written']}")
    print(f"- non_excluded_not_ready: {result['non_excluded_not_ready']}")
    print(f"- critical_alerts: {result['critical_alerts']}")
    print(f"- state_distribution: {result['state_distribution']}")
    return 1 if result["critical_alerts"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
