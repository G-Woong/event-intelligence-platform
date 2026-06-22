"""Phase F-12 Production Orchestration runner — 주기 수집 파이프라인을 닫는 통합 진입점.

흐름(설계 07/08/05/09):
  load profiles/memory/state → derive ProductionSourceState → build run plan
  → (rate-limit/quarantine/dead-end skip) → due source 실행(probe, 주입형)
  → candidate/record/signal 추출 → time normalize → quality gate
  → EventQueue dedup → EventQueue write → raw_events bridge(DB or mirror)
  → production_state 갱신 → monitoring report → critical 시에만 nonzero exit.

모드:
  - production-dry-run: 네트워크 0. state/plan/state-persist/monitoring/bridge 계약만 검증.
  - production-validation: due source를 실제 probe(force=False, no bypass)해 raw_events까지 흘린다.

네트워크는 전부 probe_fn 경유(주입 가능). 신규 설치 0. secret 미출력.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ingestion.core.env_loader import load_env
from ingestion.orchestration.bridge_to_raw_events import (
    RawEventBridgeWriter,
    bridge_records,
)
from ingestion.orchestration.cross_source_dedup import cluster_records, summarize_clusters
from ingestion.orchestration.eventqueue_dedup import DedupIndex
from ingestion.orchestration.monitoring import (
    build_monitoring_summary,
    write_monitoring_report,
)
from ingestion.orchestration.production_scheduler import (
    MODE_DRY_RUN,
    MODE_VALIDATION,
    build_production_run_plan,
)
from ingestion.orchestration.production_state import (
    derive_production_state,
    load_production_state,
    save_production_state,
    summarize_states,
)
from ingestion.orchestration.quality_pre_gate import evaluate_pre_gate
from ingestion.orchestration.rate_limit_governor import (
    RateLimitGovernor,
    detect_rate_limit_signal,
)
from ingestion.orchestration.source_profile import load_source_profiles
from ingestion.orchestration.source_strategy_memory import load_strategy_memory
from ingestion.orchestration.time_normalizer import normalize_time, summarize_precision

_DEFAULT_PROFILES = Path("ingestion/configs/source_profiles.yaml")
_DEFAULT_MEMORY = Path("ingestion/configs/source_strategy_memory.yaml")
_DEFAULT_STATE = Path("ingestion/outputs/state/production_source_state.json")
_DEFAULT_QUEUE = Path("ingestion/outputs/jsonl/production_event_queue.jsonl")
_DEFAULT_RAW_MIRROR = Path("ingestion/outputs/raw_events/raw_events_mirror.jsonl")
_DEFAULT_DEDUP_INDEX = Path("ingestion/outputs/state/eventqueue_dedup_index.json")
_DEFAULT_GOVERNOR = Path("ingestion/outputs/state/rate_limit_governor.json")
_DEFAULT_MONITORING = Path("ingestion/outputs/monitoring")

# source_group + numeric_exempt → EventQueue record_type
_GROUP_TO_RECORD_TYPE = {
    "official": "official_record",
    "domain": "official_record",
    "search": "search_result",
    "community": "community_signal",
    "market": "structured_signal",
    "trend": "structured_signal",
    "news": "article_candidate",
}


def _infer_fmt(path, text: str) -> str:
    """artifact 파일 확장자/내용으로 파서 포맷 추론(json/xml/html)."""
    low = str(path).lower()
    if low.endswith((".xml", ".rss", ".atom")):
        return "xml"
    if low.endswith(".json"):
        return "json"
    if low.endswith((".html", ".htm")):
        return "html"
    head = text.lstrip()[:1]
    if head in ("{", "["):
        return "json"
    if head == "<":
        # <?xml 또는 <rss/<feed → xml, 그 외 → html
        low_head = text.lstrip()[:200].lower()
        if "<?xml" in low_head or "<rss" in low_head or "<feed" in low_head:
            return "xml"
        return "html"
    return "json"


def _record_type_for(profile, candidate) -> str:
    if getattr(candidate, "numeric_payload_exempt", False):
        return "structured_signal"
    grp = getattr(profile, "source_group", None) or "news"
    return _GROUP_TO_RECORD_TYPE.get(grp, "article_candidate")


@dataclass
class ProductionRunConfig:
    mode: str = MODE_DRY_RUN
    profiles_path: Path = _DEFAULT_PROFILES
    memory_path: Path = _DEFAULT_MEMORY
    state_path: Path = _DEFAULT_STATE
    queue_path: Path = _DEFAULT_QUEUE
    raw_mirror_path: Path = _DEFAULT_RAW_MIRROR
    dedup_index_path: Path = _DEFAULT_DEDUP_INDEX
    governor_path: Path = _DEFAULT_GOVERNOR
    monitoring_dir: Path = _DEFAULT_MONITORING
    max_sources: Optional[int] = None
    all_due: bool = False
    force: bool = False
    respect_rate_limit: bool = True


@dataclass
class _Collected:
    eq_records: list = field(default_factory=list)
    record_type_counts: dict = field(default_factory=dict)
    body_present: int = 0
    times: list = field(default_factory=list)
    error_by_source: dict = field(default_factory=dict)
    error_by_root_cause: dict = field(default_factory=dict)
    rate_limited_sources: list = field(default_factory=list)
    # source_id → "success" | "failure" | "rate_limited" (실패 누적/격리 판정용)
    outcomes: dict = field(default_factory=dict)
    failure_category: dict = field(default_factory=dict)


def _build_api_ready_map(profiles, env_path: Optional[Path]) -> dict:
    """source_id → keys_present(bool). 키 값은 읽지 않고 존재 여부만."""
    try:
        from ingestion.orchestration.api_readiness import audit_api_key_readiness
        results = audit_api_key_readiness(profiles, env_path=env_path)
        return {r.source_id: bool(getattr(r, "keys_present", False)) for r in results}
    except Exception:
        return {}


def _iso_now(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


_SUCCESS_PROBE_STATUSES = frozenset({"LIVE_SUCCESS", "LIVE_PARTIAL", "PARTIAL", "SUCCESS"})


def _extract_eq_records_for_source(profile, probe_result, collected: _Collected) -> None:
    """probe 결과 artifact를 파싱해 EventQueue record로 변환(quality gate 통과분만)."""
    from ingestion.orchestration.artifact_parser import parse_artifact_text
    from ingestion.orchestration.full_source_revival import build_eventqueue_record

    sid = profile.source_id
    paths = getattr(probe_result, "artifact_paths", None)
    text = None
    fmt = "json"
    chosen_path = None
    for attr in ("raw_payload", "extracted_payload", "raw_html", "raw_signal"):
        p = getattr(paths, attr, None) if paths else None
        if p and Path(p).exists():
            try:
                text = Path(p).read_text(encoding="utf-8")
                fmt = _infer_fmt(p, text)
                chosen_path = p
                break
            except OSError:
                continue
    if not text:
        collected.error_by_source[sid] = "no_artifact_text"
        return
    try:
        candidates, parser_name, _errs = parse_artifact_text(
            text, source_id=sid,
            collection_status=getattr(probe_result, "status", "UNKNOWN"),
            confirmation_policy=getattr(profile, "confirmation_policy", "standard"),
            raw_artifact_path=chosen_path, fmt=fmt,
        )
    except Exception as exc:  # 파서 예외 격리
        collected.error_by_source[sid] = f"parse_error:{type(exc).__name__}"
        return

    for c in candidates:
        gate = evaluate_pre_gate(
            c, purpose=getattr(profile, "purpose", None),
            source_group=getattr(profile, "source_group", None),
            confirmation_policy=getattr(profile, "confirmation_policy", None),
        )
        if gate.decision == "reject":
            continue
        rt = _record_type_for(profile, c)
        # 본문 길이/상태(둔갑 금지) — present만 카운트
        from ingestion.orchestration.body_state import assess_body_state
        bstate = assess_body_state(
            body_text=c.body_text, summary=c.summary,
            purpose=getattr(profile, "purpose", None),
            numeric_payload_exempt=c.numeric_payload_exempt, parse_error=c.parse_error,
        )
        if bstate.extraction_status == "present":
            collected.body_present += 1
        nt = normalize_time(c.published_at, source_field="published_at")
        collected.times.append(nt)
        # structured signal은 dedup 키 granularity를 위해 실제 signal type을 싣는다
        # (리터럴 "structured_signal"을 쓰면 같은 소스 같은 시각의 다른 지표가 과병합됨)
        signal_label = getattr(profile, "purpose", None) or getattr(profile, "source_group", None) or "signal"
        rec = build_eventqueue_record(
            record_type=rt, source_id=sid,
            title_or_label=c.title,
            source_url_or_evidence=(c.source_url or c.canonical_url),  # 외부 URL만(로컬 경로 둔갑 금지)
            canonical_url=c.canonical_url,
            published_at_or_observed_at=(nt.value or c.published_at),
            body_state_or_signal=(signal_label if rt == "structured_signal" else bstate.extraction_status),
            confirmation_policy=c.confirmation_policy,
            quality_pre_gate_decision=gate.decision,
        )
        collected.record_type_counts[rt] = collected.record_type_counts.get(rt, 0) + 1
        collected.eq_records.append(rec)


def run_production_orchestration(
    config: ProductionRunConfig,
    *,
    profiles=None,
    memory=None,
    prior_states=None,
    probe_fn: Optional[Callable] = None,
    db_writer=None,
    api_ready_map: Optional[dict] = None,
    governor: Optional[RateLimitGovernor] = None,
    now: Optional[datetime] = None,
    env_path: Optional[Path] = None,
    run_id: Optional[str] = None,
    write_outputs: bool = True,
) -> dict:
    """production orchestration 1회 실행. result dict 반환(critical_alerts 포함).

    probe_fn(source_id, *, max_items, force) -> probe_result(.status, .artifact_paths, .error_category).
    dry-run 모드 또는 probe_fn=None이면 네트워크 없이 state/plan/monitoring/bridge 계약만 검증.
    """
    now = now or datetime.now(timezone.utc)
    run_id = run_id or _iso_now(now).replace(":", "").replace("-", "")
    profiles = profiles if profiles is not None else load_source_profiles(str(config.profiles_path))
    memory = memory if memory is not None else load_strategy_memory(str(config.memory_path))
    api_ready_map = api_ready_map if api_ready_map is not None else _build_api_ready_map(profiles, env_path)
    governor = governor or RateLimitGovernor(state_path=config.governor_path if write_outputs else None)
    prior = prior_states if prior_states is not None else load_production_state(config.state_path)

    # 1) derive states (prior failure counts 보존)
    states = []
    for p in profiles:
        prev = prior.get(p.source_id)
        states.append(derive_production_state(
            p, memory=memory, api_key_ready=api_ready_map.get(p.source_id, False),
            last_success_at=(prev.last_success_at if prev else None),
            last_failure_at=(prev.last_failure_at if prev else None),
            failure_count=(prev.failure_count if prev else 0),
            consecutive_failure_count=(prev.consecutive_failure_count if prev else 0),
        ))
    states_by_id = {s.source_id: s for s in states}

    # last_run_at (prior last_success_at) → is_due cadence 레이어 입력(governor와 이중 게이트)
    last_run_at_by_source: dict = {}
    for sid, st in (prior or {}).items():
        dt = _parse_iso(getattr(st, "last_success_at", None))
        if dt is not None:
            last_run_at_by_source[sid] = dt

    # 2) run plan
    mode = config.mode
    plan_mode = MODE_VALIDATION if config.all_due else mode
    plan = build_production_run_plan(
        profiles, states=states_by_id, memory=memory, governor=governor,
        last_run_at_by_source=last_run_at_by_source,
        now=now, mode=plan_mode, max_sources=config.max_sources, run_id=run_id,
    )

    collected = _Collected()
    eventqueue_failed = 0

    # 3) due source 실행 (probe 있을 때만; dry-run은 probe 생략)
    live = (mode != MODE_DRY_RUN) and (probe_fn is not None)
    if live:
        for sid in plan.due_sources:
            profile = next((p for p in profiles if p.source_id == sid), None)
            if profile is None:
                continue
            governor.record_call(sid, now=now)
            try:
                probe_result = probe_fn(sid, max_items=5, force=config.force)
            except Exception as exc:  # source 격리 — 한 source 실패가 전체를 멈추지 않음
                collected.error_by_source[sid] = f"probe_exception:{type(exc).__name__}"
                collected.outcomes[sid] = "failure"
                collected.failure_category[sid] = "PROBE_EXCEPTION"
                continue
            status = getattr(probe_result, "status", "UNKNOWN")
            err_cat = getattr(probe_result, "error_category", None)
            # rate-limit 감지 → 쿨다운 설정(무한 retry 금지)
            if status == "RATE_LIMITED" or detect_rate_limit_signal(
                http_status=getattr(probe_result, "http_status", None)
            ):
                governor.record_rate_limited(
                    sid, freshness_bucket=getattr(profile, "freshness_bucket", "short"),
                    reason="probe_rate_limited", now=now,
                )
                collected.rate_limited_sources.append(sid)
                collected.outcomes[sid] = "rate_limited"
                collected.error_by_root_cause["RATE_LIMITED"] = (
                    collected.error_by_root_cause.get("RATE_LIMITED", 0) + 1
                )
                continue
            if err_cat:
                collected.error_by_root_cause[err_cat] = (
                    collected.error_by_root_cause.get(err_cat, 0) + 1
                )
            # 성공/실패 판정 — 실패는 consecutive_failure_count 누적 → quarantine 트리거
            if status in _SUCCESS_PROBE_STATUSES:
                collected.outcomes[sid] = "success"
            else:
                collected.outcomes[sid] = "failure"
                collected.failure_category[sid] = err_cat or status
            _extract_eq_records_for_source(profile, probe_result, collected)

    # 4) EventQueue dedup
    dedup_index = DedupIndex(path=config.dedup_index_path if write_outputs else None)
    written_records = []
    duplicates_skipped = 0
    dedup_basis_counts: dict = {}
    for i, rec in enumerate(collected.eq_records):
        decision = dedup_index.decide(rec, ref=f"{run_id}:{i}")
        basis = (decision.reason or "unknown").split(":")[-1]
        dedup_basis_counts[basis] = dedup_basis_counts.get(basis, 0) + 1
        if decision.is_duplicate:
            duplicates_skipped += 1
            continue
        rec = dict(rec)
        rec["_dedup_key"] = decision.record_key
        written_records.append(rec)

    # 5) cross-source dedup (보고/클러스터; possible_duplicate는 hold)
    clusters = cluster_records(written_records)
    cluster_summary = summarize_clusters(clusters)

    # 6) EventQueue write (gitignored jsonl)
    if write_outputs and written_records:
        try:
            config.queue_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config.queue_path, "a", encoding="utf-8") as f:
                for rec in written_records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            eventqueue_failed = len(written_records)

    # 7) raw_events bridge (DB or mirror)
    writer = RawEventBridgeWriter(
        mirror_path=(config.raw_mirror_path if (write_outputs and db_writer is None) else None),
        db_writer=db_writer,
    )
    bridge_result = bridge_records(written_records, writer=writer, collected_at=_iso_now(now))

    # 8) production state 갱신 (probe 결과 → 실패 누적/quarantine, governor cooldown 반영)
    from ingestion.orchestration.quarantine import evaluate_quarantine
    now_iso = _iso_now(now)
    final_states = []
    for s in states:
        patch: dict = {}
        outcome = collected.outcomes.get(s.source_id)
        # 8a) probe 결과로 실패 카운트 갱신 + 임계 도달 시 quarantine(F-4 배선)
        if outcome == "success":
            patch.update(last_success_at=now_iso, consecutive_failure_count=0)
        elif outcome == "failure":
            consec = s.consecutive_failure_count + 1
            patch.update(
                last_failure_at=now_iso, failure_count=s.failure_count + 1,
                consecutive_failure_count=consec,
            )
            q = evaluate_quarantine(
                s.source_id, last_status=s.current_status,
                error_category=collected.failure_category.get(s.source_id),
                consecutive_failure_count=consec, now=now,
            )
            if q.quarantined:
                patch.update(current_status="QUARANTINED", production_ready=False,
                             quarantine_until=q.quarantine_until,
                             terminal_reason=q.reason)
        # 8b) governor cooldown(rate-limit) 반영
        cd = governor.cooldown_until(s.source_id)
        if cd and s.current_status not in ("POLICY_EXCLUDED",) and not patch.get("quarantine_until"):
            patch.update(cooldown_until=cd, rate_limit_status="cooldown",
                         production_ready=False,
                         current_status=("COOLDOWN" if s.production_ready else s.current_status))
        if patch:
            s = type(s)(**{**s.to_dict(), **patch})
        final_states.append(s)
    if write_outputs:
        save_production_state(final_states, config.state_path, run_id=run_id)
        if governor._path:
            governor.save()

    # 9) monitoring
    summary = build_monitoring_summary(
        run_id=run_id, plan=plan, source_states=final_states,
        records_collected=len(collected.eq_records),
        eventqueue_written=len(written_records),
        duplicates_skipped=duplicates_skipped,
        bridge_result=bridge_result,
        record_type_counts=collected.record_type_counts,
        body_present_count=collected.body_present,
        time_precision=summarize_precision(collected.times),
        eventqueue_failed=eventqueue_failed,
        queue_or_raw_sample=written_records,  # 전수 secret 스캔(부분 표본 blind spot 제거)
        error_by_source=collected.error_by_source,
        error_by_root_cause=collected.error_by_root_cause,
    )
    summary["eventqueue_dedup_basis"] = dedup_basis_counts
    summary["cross_source_clusters"] = cluster_summary
    summary["dedup_index_size"] = dedup_index.size()
    monitoring_paths = {}
    if write_outputs:
        monitoring_paths = write_monitoring_report(
            summary, final_states, monitoring_dir=config.monitoring_dir, run_id=run_id,
        )
        if write_outputs and config.dedup_index_path:
            dedup_index.save()

    state_summary = summarize_states(final_states)
    return {
        "run_id": run_id,
        "mode": mode,
        "plan": plan,
        "summary": summary,
        "monitoring_paths": monitoring_paths,
        "source_without_state": state_summary["source_without_state"],
        "unknown_root_cause": state_summary["unknown"],
        "critical_alerts": summary["critical_alert_count"],
        "raw_events_bridge_contract_pass": bridge_result.get("bridge_contract_pass", False),
        "dedup_index_functional": True,
        "production_state_written": write_outputs,
        "monitoring_written": bool(monitoring_paths),
        "states": final_states,
        "bridge_result": bridge_result,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Phase F production orchestration runner")
    ap.add_argument("--mode", default="production-dry-run",
                    choices=["production-dry-run", "production-validation"])
    ap.add_argument("--state-path", default=str(_DEFAULT_STATE))
    ap.add_argument("--event-queue-path", default=str(_DEFAULT_QUEUE))
    ap.add_argument("--raw-events-mirror", default=str(_DEFAULT_RAW_MIRROR))
    ap.add_argument("--monitoring-dir", default=str(_DEFAULT_MONITORING))
    ap.add_argument("--max-sources", type=int, default=None)
    ap.add_argument("--all-due", action="store_true")
    ap.add_argument("--force", default="false")
    ap.add_argument("--respect-rate-limit", default="true")
    ap.add_argument("--env-path", default=None)
    ap.add_argument("--no-live", action="store_true",
                    help="validation 모드라도 네트워크 probe 비활성(계약 검증만)")
    # P0: raw_events sink 선택. 기본은 mirror(기존 동작 보존). backend 선택 시 실 raw_events PG +
    # Redis Stream 으로 적재(BackendApiRawEventsWriter 주입). 우회/가정 없음.
    ap.add_argument("--raw-events-sink", default="mirror", choices=["mirror", "backend"],
                    help="raw_events 적재 대상: mirror(jsonl, 기본) | backend(PG+Redis via API)")
    ap.add_argument("--backend-url", default="http://localhost:8000")
    return ap


def _real_probe_fn():
    """기존 run_collection_probe를 production runner 시그니처로 어댑트."""
    from ingestion.fetch_strategies.collection_probe import run_collection_probe

    def _probe(source_id, *, max_items=5, force=False):
        return run_collection_probe(source_id, max_items=max_items, force=force)
    return _probe


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    config = ProductionRunConfig(
        mode=args.mode,
        state_path=Path(args.state_path),
        queue_path=Path(args.event_queue_path),
        raw_mirror_path=Path(args.raw_events_mirror),
        monitoring_dir=Path(args.monitoring_dir),
        max_sources=args.max_sources,
        all_due=bool(args.all_due),
        force=str(args.force).lower() == "true",
        respect_rate_limit=str(args.respect_rate_limit).lower() == "true",
    )
    env_path = Path(args.env_path) if args.env_path else None

    # R-EnvLoadAsymmetry: make the .env contract explicit at the CLI entrypoint instead
    # of relying solely on audit_api_key_readiness' load side-effect (idempotent
    # setdefault). The injectable run_production_orchestration() core used by tests is
    # unchanged. Values are never read or printed.
    load_env(env_path)

    # plan 미리보기 출력(실행 전)
    profiles = load_source_profiles(str(config.profiles_path))
    memory = load_strategy_memory(str(config.memory_path))
    api_ready = _build_api_ready_map(profiles, env_path)
    now = datetime.now(timezone.utc)
    states = {p.source_id: derive_production_state(
        p, memory=memory, api_key_ready=api_ready.get(p.source_id, False)) for p in profiles}
    preview_plan = build_production_run_plan(
        profiles, states=states, memory=memory,
        now=now, mode=(MODE_VALIDATION if config.all_due else config.mode),
        max_sources=config.max_sources, run_id="preview")
    cats = preview_plan.skip_category_counts
    print("PRODUCTION_ORCHESTRATION_PLAN:")
    print(f"- total_sources: {len(profiles)}")
    print(f"- due_sources: {len(preview_plan.due_sources)}")
    print(f"- skipped_policy: {cats.get('skipped_policy', 0)}")
    print(f"- skipped_cooldown: {cats.get('skipped_cooldown', 0)}")
    print(f"- skipped_quarantine: {cats.get('skipped_quarantine', 0)}")
    print(f"- skipped_dead_end: {cats.get('skipped_dead_end', 0)}")
    print(f"- expected_calls: {preview_plan.expected_calls}")
    print(f"- state_path: {config.state_path}")
    print(f"- queue_path: {config.queue_path}")

    # P0: raw_events sink — backend 선택 시 실 PG+Redis 적재기 주입(없으면 mirror)
    db_writer = None
    if args.raw_events_sink == "backend":
        import os
        from ingestion.integration.raw_events_writer import BackendApiRawEventsWriter
        db_writer = BackendApiRawEventsWriter(
            base_url=args.backend_url, admin_token=os.getenv("ADMIN_API_TOKEN") or None,
        )
        print(f"- raw_events_target: backend({args.backend_url}) PG+Redis")
    else:
        print(f"- raw_events_target: mirror({config.raw_mirror_path})")
    print(f"- monitoring_dir: {config.monitoring_dir}")

    probe_fn = None
    if config.mode == "production-validation" and not args.no_live:
        probe_fn = _real_probe_fn()

    result = run_production_orchestration(
        config, profiles=profiles, memory=memory, probe_fn=probe_fn,
        db_writer=db_writer,
        api_ready_map=api_ready, now=now, env_path=env_path,
    )
    s = result["summary"]
    print("\nPRODUCTION_ORCHESTRATION_RESULT:")
    print(f"- attempted: {s['attempted_sources']}")
    print(f"- success: {s['records_collected']}")
    print(f"- skipped: {len(result['plan'].skipped_sources)}")
    print(f"- rate_limited: {s['rate_limited']}")
    print(f"- quarantined: {s['quarantined']}")
    print(f"- records_extracted: {s['records_collected']}")
    print(f"- duplicates_skipped: {s['duplicates_skipped']}")
    print(f"- eventqueue_written: {s['records_enqueued']}")
    print(f"- raw_events_written: {s['raw_events_written']}")
    print(f"- monitoring_alerts: {len(s['alerts'])}")
    print(f"- critical_alerts: {s['critical_alert_count']}")
    print(f"- source_without_state: {result['source_without_state']}")
    print(f"- unknown_root_cause: {result['unknown_root_cause']}")
    print(f"- raw_events_bridge_contract_pass: {result['raw_events_bridge_contract_pass']}")

    # critical infra 실패에만 nonzero exit
    return 1 if result["critical_alerts"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
