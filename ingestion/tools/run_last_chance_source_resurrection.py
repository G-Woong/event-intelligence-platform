"""Phase G2-13 Last-chance source resurrection runner — dcinside/google_trends_explore/gdelt.

세 source를 조기 포기하지 않고, 정책 준수 범위에서 복구한다.
  dcinside  : robots 허용 갤러리 static fetch → community_signal (우회 0; Cloudflare/captcha면 중단)
  gdelt     : RateLimitGovernor min_interval/cooldown + query 단순화 spaced probe → pending_resume
  g_trends  : 공식 API 없음 + anti-abuse 429 → REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT (문서화된 blocker)

검증된 live record만 EventQueue dedup + raw_events mirror로 적재한다(둔갑 금지).
모든 외부 호출은 주입형 → 단위 테스트 네트워크 0. 신규 설치 0. secret 미출력.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ingestion.orchestration.bridge_to_raw_events import RawEventBridgeWriter, bridge_records
from ingestion.orchestration.dcinside_strategy import collect_dcinside, list_url_for
from ingestion.orchestration.eventqueue_dedup import DedupIndex
from ingestion.orchestration.gdelt_strategy import collect_gdelt
from ingestion.orchestration.google_trends_strategy import assess_google_trends
from ingestion.orchestration.last_chance_source_resurrection import (
    NEEDS_OPERATOR_REVIEW,
    PENDING_RESUME,
    POLICY_BLOCKED,
    PRODUCTION_READY,
    PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY,
    LastChanceSourceResurrection,
    classify_resurrection,
)
from ingestion.orchestration.monitoring import build_monitoring_summary, write_monitoring_report
from ingestion.orchestration.production_scheduler import ProductionRunPlan
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.orchestration.source_policy_probe import probe_source_policy
from ingestion.orchestration.source_strategy_memory import (
    SourceStrategyMemory,
    load_strategy_memory,
    save_strategy_memory,
)

_TARGETS = ("dcinside", "google_trends_explore", "gdelt")
_DC_GALLERY = "stockus"   # robots(User-agent:*) 허용 갤러리(주식 미국장) — 차단 목록에 없음

_MEMORY = Path("ingestion/configs/source_strategy_memory.yaml")
_QUEUE = Path("ingestion/outputs/jsonl/last_chance_event_queue.jsonl")
_RAW_MIRROR = Path("ingestion/outputs/raw_events/last_chance_raw_events_mirror.jsonl")
_DEDUP = Path("ingestion/outputs/state/eventqueue_dedup_index.json")
_GDELT_RL = Path("ingestion/outputs/state/gdelt_rate_limit_state.json")
_MONITORING = Path("ingestion/outputs/monitoring")
_OUTDIR = Path("ingestion/outputs/tmp_last_chance_source_resurrection")
_EXTRACTED = Path("ingestion/outputs/extracted_payload")
_RENDERED = Path("ingestion/outputs/rendered_dom")


def _iso_now(now=None):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _historical_evidence(sid: str) -> Optional[str]:
    """과거 성공 흔적을 '파일 개수'로만 기록(원문 미열람)."""
    parts = []
    for label, base in (("extracted_payload", _EXTRACTED), ("rendered_dom", _RENDERED)):
        d = base / sid
        if d.is_dir():
            try:
                n = sum(1 for _ in d.iterdir())
            except OSError:
                n = 0
            if n:
                parts.append(f"{label}={n}")
    return "; ".join(parts) if parts else None


# ── per-source resurrection ──────────────────────────────────────────────────
def _resurrect_dcinside(*, robots_get, dcinside_collect) -> tuple[LastChanceSourceResurrection, list, Optional[SourceStrategyMemory], Optional[dict]]:
    url = list_url_for(_DC_GALLERY, minor=True)
    probe = probe_source_policy(source_id="dcinside", tested_url=url, robots_get=robots_get)
    ladder = ("historical_artifact_replay", "robots_allowed_static_list_fetch")
    res = dcinside_collect()
    attempts = (f"static_fetch:{_DC_GALLERY}",)

    if res.success and res.records:
        # 적대 리뷰 흡수: 본문 0(list preview only) + AI-차단 robots를 generic UA로 통과 + ToS 자동수집
        # 미검증 → 데이터는 alive지만 degraded로 정직히 표기(root_cause_after 비우지 않음 → DEGRADED).
        # 검증 범위는 stockus 단일 갤러리로 한정(일반화 금지). 작성자 닉네임(PII)은 수집하지 않음.
        caveats = ("LIST_PREVIEW_ONLY_NO_BODY", "AI_CRAWLER_ROBOTS_BLOCK_HONORED_GENERIC_UA",
                   "TOS_AUTOMATED_USE_UNVERIFIED", "SCOPE_SINGLE_GALLERY_STOCKUS")
        memory = SourceStrategyMemory(
            source_id="dcinside", previous_status="MVP_EXCLUDED",
            final_status="COMMUNITY_SIGNAL_ALIVE",
            root_cause_before=("ROBOTS_OR_POLICY_BLOCK_OVERCAUTIOUS",),
            root_cause_after=caveats,
            successful_strategy="robots_allowed_static_list_fetch",
            preferred_next_strategy="robots_allowed_static_list_fetch",
            parser_notes="dcinside_list_community_signal;no_pii_nickname;list_meta_only",
            cooldown_policy="respect_min_interval", safety_policy="no_bypass",
            evidence=(f"gallery={_DC_GALLERY}_only;items={res.item_count};"
                      "robots_user_agent_star_allow;ai_training_crawler_block_honored_via_generic_ua;"
                      "tos_automated_use_unverified;list_preview_only_no_body;no_bypass"),
        )
        patch = {"enabled": True, "profile_status": "active",
                 "readiness_status": "DEGRADED_PREVIEW_ONLY",
                 "live_eligible": "true", "skip_reason": "none",
                 "preferred_strategy": "robots_allowed_static_list_fetch",
                 "notes": "Phase G-2: stockus gallery only (robots User-agent:* allow); AI-training "
                          "crawler block honored via generic UA (no bypass); ToS automated-use UNVERIFIED "
                          "(legal-safety review pending); list-level community_signal only, no body, no PII"}
        rec = LastChanceSourceResurrection(
            "dcinside", "MVP_EXCLUDED", "robots_or_policy_block",
            _historical_evidence("dcinside"), probe, ladder, attempts,
            "robots_allowed_static_list_fetch", res.item_count, 0,
            PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY, None,
            "list_preview_only_no_body;ai_block_honored_generic_ua;tos_unverified;scope=stockus_only")
        return rec, list(res.records), memory, patch

    # 우회가 필요한 차단(Cloudflare/captcha/login)이면 정직한 policy blocker
    if res.verdict in ("CLOUDFLARE_BLOCKED_NO_BYPASS", "CAPTCHA_BLOCKED_NO_BYPASS",
                       "LOGIN_BLOCKED_NO_BYPASS"):
        ev = f"{res.verdict}:{res.blocked_reason};no_bypass"
        rec = LastChanceSourceResurrection(
            "dcinside", "MVP_EXCLUDED", "robots_or_policy_block",
            _historical_evidence("dcinside"), probe, ladder, attempts, None, 0, 0,
            POLICY_BLOCKED, None, ev)
        return rec, [], None, None

    if res.verdict == "EXTERNAL_RATE_LIMITED_PENDING_RESUME":
        rec = LastChanceSourceResurrection(
            "dcinside", "MVP_EXCLUDED", "robots_or_policy_block",
            _historical_evidence("dcinside"), probe, ladder, attempts, None, 0, 0,
            PENDING_RESUME, None, "provider_rate_limited_retry_next_run")
        return rec, [], None, None

    rec = LastChanceSourceResurrection(
        "dcinside", "MVP_EXCLUDED", "robots_or_policy_block",
        _historical_evidence("dcinside"), probe, ladder, attempts, None, 0, 0,
        NEEDS_OPERATOR_REVIEW, None, f"{res.verdict}:{res.blocked_reason}")
    return rec, [], None, None


def _resurrect_gdelt(*, governor, gdelt_collect) -> tuple[LastChanceSourceResurrection, list, Optional[SourceStrategyMemory], Optional[dict]]:
    res = gdelt_collect(governor)
    ladder = ("rate_limit_cooldown_check", "query_simplification_spaced_probe")
    if res.success and res.records:
        memory = SourceStrategyMemory(
            source_id="gdelt", previous_status="EXTERNAL_RATE_LIMITED",
            final_status="OFFICIAL_RECORD_ALIVE", root_cause_before=("RATE_LIMITED",),
            successful_strategy="query_simplification_spaced_probe",
            preferred_next_strategy="query_simplification_spaced_probe",
            cooldown_policy="respect_cooldown", safety_policy="no_bypass",
            evidence=f"attempts={','.join(res.attempts)};items={res.item_count}")
        patch = {"enabled": True, "profile_status": "active", "readiness_status": "CORE_READY",
                 "live_eligible": "true"}
        rec = LastChanceSourceResurrection(
            "gdelt", "EXTERNAL_RATE_LIMITED", "rate_limited", _historical_evidence("gdelt"),
            None, ladder, res.attempts, "query_simplification_spaced_probe",
            res.item_count, 0, PRODUCTION_READY, None, None)
        return rec, list(res.records), memory, patch

    # 429/throttle → pending_resume(자동 재개). terminal 아님.
    memory = SourceStrategyMemory(
        source_id="gdelt", previous_status="EXTERNAL_RATE_LIMITED",
        final_status="EXTERNAL_RATE_LIMITED_PENDING_RESUME", root_cause_before=("RATE_LIMITED",),
        root_cause_after=("PROVIDER_429_THROTTLE",), successful_strategy=None,
        preferred_next_strategy="rate_limit_cooldown_resume",
        cooldown_policy=f"respect_cooldown_until:{res.cooldown_until}", safety_policy="no_bypass",
        evidence=f"attempts={','.join(res.attempts) or 'cooldown_active'};next_resume_at={res.next_resume_at}")
    rec = LastChanceSourceResurrection(
        "gdelt", "EXTERNAL_RATE_LIMITED", "rate_limited", _historical_evidence("gdelt"),
        None, ladder, res.attempts, None, 0, 0, PENDING_RESUME, res.next_resume_at,
        f"provider_rate_limited;resume_at={res.next_resume_at}")
    return rec, [], memory, None


def _resurrect_google_trends(*, assess_fn) -> tuple[LastChanceSourceResurrection, list, Optional[SourceStrategyMemory], Optional[dict]]:
    a = assess_fn()
    memory = SourceStrategyMemory(
        source_id="google_trends_explore", previous_status="MVP_DEFERRED",
        final_status="REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT",
        root_cause_before=("NEEDS_API_INTEGRATION",),
        root_cause_after=("NO_OFFICIAL_API", "ANTI_ABUSE_429"),
        successful_strategy=None, preferred_next_strategy="requires_official_api_or_contract",
        safety_policy="no_bypass", evidence=a.hard_blocker_evidence)
    patch = {"enabled": False, "profile_status": "disabled",
             "readiness_status": "REQUIRES_OFFICIAL_API_OR_CONTRACT",
             "live_eligible": "false", "skip_reason": "requires_official_api_or_contract",
             "notes": f"no official API; explore endpoint anti-abuse 429; no-bypass; "
                      f"trending covered by {a.trending_covered_by}"}
    ladder = ("robots_probe", "official_api_check", "pytrends_check")
    rec = LastChanceSourceResurrection(
        "google_trends_explore", "MVP_DEFERRED", "needs_api_integration",
        _historical_evidence("google_trends_explore"), None, ladder,
        ("official_api_absent", "anti_abuse_429_observed"), None, 0, 0,
        a.final_status, None, a.hard_blocker_evidence)
    return rec, [], memory, patch


# ── 메인 ─────────────────────────────────────────────────────────────────────
def run_last_chance_source_resurrection(
    *,
    memory_path: Path = _MEMORY,
    queue_path: Path = _QUEUE,
    raw_mirror_path: Path = _RAW_MIRROR,
    dedup_index_path: Path = _DEDUP,
    gdelt_rl_path: Path = _GDELT_RL,
    monitoring_dir: Path = _MONITORING,
    output_dir: Path = _OUTDIR,
    robots_get: Optional[Callable] = None,
    dcinside_collect: Optional[Callable] = None,
    gdelt_collect: Optional[Callable] = None,
    google_trends_assess: Optional[Callable] = None,
    gdelt_min_interval_seconds: int = 10,
    gdelt_max_probes: int = 3,
    apply_config: bool = True,
    write_outputs: bool = True,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    run_id = run_id or _iso_now(now).replace(":", "").replace("-", "")

    # 주입 기본값(실 네트워크) — 테스트는 주입으로 대체
    if robots_get is None:
        robots_get = _default_robots_get
    if dcinside_collect is None:
        dcinside_collect = lambda: collect_dcinside(gallery_id=_DC_GALLERY, minor=True, robots_allowed=True)
    if gdelt_collect is None:
        def gdelt_collect(gov):
            return collect_gdelt(governor=gov, min_interval_seconds=gdelt_min_interval_seconds,
                                 max_probes=gdelt_max_probes, now=now, sleep=time.sleep)
    if google_trends_assess is None:
        google_trends_assess = assess_google_trends

    governor = RateLimitGovernor(state_path=(gdelt_rl_path if write_outputs else None))

    results: list[LastChanceSourceResurrection] = []
    eq_records: list[dict] = []
    memory_updates: list[SourceStrategyMemory] = []
    profile_patches: dict = {}

    for builder in (
        lambda: _resurrect_dcinside(robots_get=robots_get, dcinside_collect=dcinside_collect),
        lambda: _resurrect_google_trends(assess_fn=google_trends_assess),
        lambda: _resurrect_gdelt(governor=governor, gdelt_collect=gdelt_collect),
    ):
        rec, recs, mem, patch = builder()
        results.append(rec)
        if recs:
            eq_records.extend(recs)
        if mem is not None:
            memory_updates.append(mem)
        if patch is not None:
            profile_patches[rec.source_id] = patch

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

    # per-source raw_events 카운트 반영(보고용)
    raw_by_source: dict = {}
    for rec in written:
        raw_by_source[rec["source_id"]] = raw_by_source.get(rec["source_id"], 0) + 1
    results = [
        _with_raw_count(r, raw_by_source.get(r.source_id, 0)) for r in results
    ]

    # canonical memory 갱신(검증/결정 반영) — 기존 entries 보존 병합
    memory_written = 0
    if apply_config and memory_updates:
        existing = load_strategy_memory(str(memory_path))
        merged = dict(existing)
        for m in memory_updates:
            merged[m.source_id] = m
        save_strategy_memory(list(merged.values()), memory_path, run_id=run_id)
        memory_written = len(memory_updates)

    if write_outputs:
        governor.save()   # gdelt cooldown 영속화 → 다음 run 자동 재개

    verdict = classify_resurrection(results)

    # monitoring (3개 source 한정 plan)
    plan = ProductionRunPlan(
        run_id=run_id, created_at=_iso_now(now),
        due_sources=_TARGETS, skipped_sources=(), skipped_reasons={},
        expected_calls=len(_TARGETS), strategy_by_source={}, mode="last-chance-resurrection",
        skip_category_counts={})
    rtc: dict = {}
    for rec in written:
        rtc[rec["record_type"]] = rtc.get(rec["record_type"], 0) + 1
    summary = build_monitoring_summary(
        run_id=run_id, plan=plan, source_states=[],
        records_collected=len(eq_records), eventqueue_written=len(written),
        duplicates_skipped=duplicates, bridge_result=bridge_result,
        record_type_counts=rtc, queue_or_raw_sample=written)
    summary["verdict"] = verdict["verdict"]
    summary["production_ready"] = verdict["production_ready"]
    summary["pending_resume"] = verdict["pending_resume"]
    summary["hard_blockers"] = verdict["hard_blockers"]

    monitoring_paths = {}
    if write_outputs:
        out = output_dir / run_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "resurrection_result.json").write_text(
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
        "monitoring_paths": monitoring_paths, "summary": summary,
    }


def _with_raw_count(r: LastChanceSourceResurrection, n: int) -> LastChanceSourceResurrection:
    if r.raw_events_records == n:
        return r
    from dataclasses import replace
    return replace(r, raw_events_records=n)


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
    ap = argparse.ArgumentParser(description="Phase G-2 last-chance source resurrection")
    ap.add_argument("--no-apply", action="store_true", help="canonical config 미갱신(드라이런)")
    ap.add_argument("--no-outputs", action="store_true", help="outputs 미기록")
    ap.add_argument("--gdelt-min-interval-seconds", type=int, default=10)
    ap.add_argument("--gdelt-max-probes", type=int, default=3)
    args = ap.parse_args(argv)

    print("LAST_CHANCE_SOURCE_RESURRECTION_PLAN:")
    print(f"- sources: {list(_TARGETS)}")
    print("- previous_status: dcinside=MVP_EXCLUDED, google_trends_explore=MVP_DEFERRED, gdelt=EXTERNAL_RATE_LIMITED")
    print(f"- gdelt_min_interval_seconds: {args.gdelt_min_interval_seconds}, max_probes: {args.gdelt_max_probes}")
    print("- no_bypass: True (robots-allowed paths only; respect cooldown; stop on captcha/login/cloudflare)")

    result = run_last_chance_source_resurrection(
        apply_config=not args.no_apply, write_outputs=not args.no_outputs,
        gdelt_min_interval_seconds=args.gdelt_min_interval_seconds,
        gdelt_max_probes=args.gdelt_max_probes)

    print("\nLAST_CHANCE_SOURCE_RESURRECTION_RESULT:")
    print(f"- verdict: {result['verdict']['verdict']}")
    for r in result["results"]:
        print(f"- {r.source_id}: final_status={r.final_status} "
              f"eq={r.eventqueue_records} raw={r.raw_events_records} "
              f"resume_at={r.next_resume_at or '-'} "
              f"successful_strategy={r.successful_strategy or '-'}")
    print(f"- eventqueue_records: {result['eventqueue_written']} (dup_skipped={result['duplicates_skipped']})")
    print(f"- raw_events_records: {result['raw_events_written']} contract_pass={result['bridge_contract_pass']}")
    print(f"- critical_alerts: {result['critical_alerts']}")
    return 1 if result["critical_alerts"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
