"""소스별 본문 추출 audit CLI runner (Phase E-1).

저장된 수집 artifact를 소스별로 replay해 분해/본문/canonical/pre_gate를 실측하고,
gitignored outputs에 trace/sample/report를 남긴다. **기본은 네트워크 0(기존 artifact replay)** —
키 부재/차단/rate-limit을 우회하지 않는다. live 본문 fetch는 이 빌드에서 비활성이다.

실행 예:
  .venv/Scripts/python.exe -m ingestion.tools.run_source_body_audit \
    --scope enabled --max-items 1 --save-samples --sample-body-chars 3000 \
    --output-dir ingestion/outputs/tmp_source_body_audit

설계 출처: docs/Orchestration_Construction 04/05/09/11/12. stdlib만 사용. 신규 설치 0.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ingestion.orchestration.audit_trace import TraceRecorder
from ingestion.orchestration.source_body_audit import (
    SourceBodyAuditResult,
    audit_source_body,
    summarize_body_audits,
)
from ingestion.orchestration.source_body_report import (
    build_source_report,
    summarize_reports,
)
from ingestion.orchestration.source_profile import load_source_profiles
from ingestion.orchestration.artifact_parser import parse_artifact_text
from ingestion.orchestration.full_source_revival import (
    RevivalEvidence,
    StrategyAttemptRecord,
    build_eventqueue_record,
    build_revival_plan,
    check_eventqueue_readiness,
    classify_final_status,
    fetch_article_body,
    summarize_revival,
    to_structured_signal_candidates,
)
from ingestion.orchestration.full_source_revival import SourceRevivalResult

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_ROOTS = ("raw_payload", "raw_signal", "extracted_payload")
_FMT_BY_EXT = {".json": "json", ".xml": "xml", ".txt": "extracted_text"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _discover_artifact(source_id: str, outputs_dir: Path) -> Optional[Path]:
    """소스의 최신 artifact를 우선순위(raw_payload→raw_signal→extracted) + mtime으로 찾는다."""
    candidates: list[Path] = []
    for root in _OUTPUT_ROOTS:
        d = outputs_dir / root / source_id
        if d.is_dir():
            candidates.extend(p for p in d.iterdir() if p.is_file() and not p.name.startswith("."))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _fmt_for(path: Path) -> Optional[str]:
    return _FMT_BY_EXT.get(path.suffix.lower())


def _write_samples(result: SourceBodyAuditResult, samples_root: Path, *,
                   max_items: int, body_chars: int) -> int:
    """candidate별 meta/preview/body/raw_ref 샘플을 gitignored outputs에 기록. 저장 수 반환."""
    inspections = result.inspections[:max_items]
    if not inspections:
        return 0
    src_dir = samples_root / result.audit.source_id
    src_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for insp in inspections:
        c = insp.candidate
        st = insp.body_state
        pg = insp.pre_gate
        stem = f"candidate_{insp.index + 1:04d}"
        meta = {
            "source_id": c.source_id,
            "source_group": result.audit.source_group,
            "purpose": result.audit.purpose,
            "parser_name": c.parser_name,
            "candidate_index": insp.index,
            "title": c.title,
            "source_url": c.source_url,
            "canonical_url": c.canonical_url,
            "published_at": c.published_at,
            "body_state": st.extraction_status,
            "body_length": st.body_length,
            "body_source": st.body_source,
            "quality_pre_gate_decision": pg.decision,
            "quality_pre_gate_reasons": list(pg.reasons),
            "confirmation_policy": c.confirmation_policy,
            "publication_policy": pg.publication_policy,
            "evidence_ref": pg.evidence_ref,
            "parse_error": c.parse_error,
        }
        (src_dir / f"{stem}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        preview = (
            f"title: {c.title}\nsource_url: {c.source_url}\n"
            f"canonical_url: {c.canonical_url}\npublished_at: {c.published_at}\n"
            f"body_state: {st.extraction_status}\nsummary: {(c.summary or '')[:500]}\n"
        )
        (src_dir / f"{stem}.preview.txt").write_text(preview, encoding="utf-8")
        if c.body_text:
            body_sample = c.body_text[:body_chars]
        else:
            body_sample = f"<no body extracted: {st.extraction_status} ({st.reason})>"
        (src_dir / f"{stem}.body_sample.txt").write_text(body_sample, encoding="utf-8")
        raw_ref = (
            f"raw_artifact_path: {c.raw_artifact_path}\n"
            f"extracted_text_ref: {c.extracted_text_ref}\n"
            f"body_source_stage: {st.body_source or 'none'}\n"
        )
        (src_dir / f"{stem}.raw_ref.txt").write_text(raw_ref, encoding="utf-8")
        saved += 1
    return saved


def _in_scope(profile, scope: str, sources: list[str]) -> bool:
    if sources:
        return profile.source_id in sources
    if scope == "enabled":
        return profile.enabled
    if scope == "live_eligible":
        return profile.enabled and profile.live_eligible == "true"
    return profile.enabled


def run(args: argparse.Namespace) -> dict:
    outputs_dir = _REPO_ROOT / "ingestion" / "outputs"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_root = Path(args.output_dir) / run_id
    out_root.mkdir(parents=True, exist_ok=True)
    recorder = TraceRecorder(run_id, jsonl_path=out_root / "trace.jsonl",
                             console=not args.no_console)

    profiles = load_source_profiles()
    targets = [p for p in profiles if _in_scope(p, args.scope, args.source)]
    skipped_blocked = [p.source_id for p in profiles
                       if p.enabled and not _in_scope(p, args.scope, args.source)]

    if args.allow_network_body_fetch:
        print("[notice] --allow-network-body-fetch 요청됨 — 이 빌드는 live 본문 fetch "
              "비활성(no-bypass/no-new-network). 기존 artifact replay로 진행.")

    # ── PLAN ──
    plan = {
        "run_id": run_id,
        "total_profiles": len(profiles),
        "audit_targets": len(targets),
        "expected_live_calls": 0,
        "skipped_by_policy": len(profiles) - len(targets),
        "force": False,
        "max_items": args.max_items,
        "output_dir": str(out_root),
        "no_key_values_printed": True,
    }
    print("SOURCE_BODY_AUDIT_PLAN:")
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    samples_root = out_root / "samples"
    reports_root = out_root / "source_reports"
    reports_root.mkdir(parents=True, exist_ok=True)

    audits = []
    reports = []
    attempted = success = no_artifact = failed = 0

    for p in profiles:
        if not _in_scope(p, args.scope, args.source):
            continue
        attempted += 1
        recorder.record(p.source_id, "profile_loaded", "ok", timestamp=_now_iso(),
                        metrics={"purpose": p.purpose, "source_group": p.source_group})
        artifact = _discover_artifact(p.source_id, outputs_dir)
        text = None
        fmt = None
        artifact_type = None
        if artifact is not None:
            artifact_type = _fmt_for(artifact)
            fmt = artifact_type
            try:
                text = artifact.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = None

        result = audit_source_body(
            text, source_id=p.source_id, purpose=p.purpose,
            source_group=p.source_group, confirmation_policy=p.confirmation_policy,
            artifact_path=str(artifact) if artifact else None, fmt=fmt,
            recorder=recorder, timestamp=_now_iso(),
        )
        audit = result.audit
        audits.append(audit)

        sample_saved = 0
        if args.save_samples and result.inspections:
            sample_saved = _write_samples(result, samples_root,
                                          max_items=args.max_items,
                                          body_chars=args.sample_body_chars)
            recorder.record(p.source_id, "sample_saved", "ok", timestamp=_now_iso(),
                            metrics={"count": sample_saved})

        report = build_source_report(
            audit, enabled=p.enabled, live_eligible=p.live_eligible,
            requires_api_key=p.requires_api_key, api_key_ready=None,
            skip_reason=p.skip_reason, artifact_type=artifact_type,
            sample_saved_count=sample_saved,
        )
        reports.append(report)
        (reports_root / f"{p.source_id}.json").write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")

        if not audit.artifact_exists:
            no_artifact += 1
        elif audit.candidate_count > 0:
            success += 1
        else:
            failed += 1

    body_summary = summarize_body_audits(audits)
    readiness_summary = summarize_reports(reports)
    summary = {
        "run_id": run_id,
        "plan": plan,
        "attempted": attempted,
        "artifact_present": attempted - no_artifact,
        "decomposed_sources": success,
        "zero_or_error_sources": failed,
        "no_artifact_sources": no_artifact,
        "body_audit": body_summary,
        "readiness": readiness_summary,
        "trace_stage_counts": recorder.stage_counts(),
    }
    (out_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # summary.csv (소스별 한 줄)
    with open(out_root / "summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "source_id", "source_group", "purpose", "artifact_type", "candidate_count",
            "body_present", "body_partial", "snippet_only", "body_missing",
            "numeric_exempt", "canonical_url", "pre_gate_pass", "pre_gate_hold",
            "pre_gate_reject", "production_readiness", "parser_gap_reason",
            "body_gap_reason", "next_action",
        ])
        for r in reports:
            w.writerow([
                r.source_id, r.source_group, r.purpose, r.artifact_type, r.candidate_count,
                r.body_present_count, r.body_partial_count, r.snippet_only_count,
                r.body_missing_count, r.numeric_exempt_count, r.canonical_url_count,
                r.pre_gate_pass, r.pre_gate_hold, r.pre_gate_reject,
                r.production_readiness, r.parser_gap_reason or "", r.body_gap_reason or "",
                r.next_action,
            ])

    t = body_summary["totals"]
    result_block = {
        "attempted": attempted,
        "success_decomposed": success,
        "no_artifact": no_artifact,
        "zero_or_error": failed,
        "candidate_total": t["candidate_total"],
        "body_present": t["body_present"],
        "body_partial": t["body_partial"],
        "snippet_only": t["snippet_only"],
        "body_missing": t["body_missing"],
        "numeric_exempt": t["numeric_exempt"],
        "structured_signal": t["structured_signal"],
        "pre_gate_pass": t["pre_gate_pass"],
        "pre_gate_hold": t["pre_gate_hold"],
        "pre_gate_reject": t["pre_gate_reject"],
        "zero_decompose_sources": t["zero_decompose_sources"],
        "readiness_distribution": readiness_summary["readiness_distribution"],
    }
    print("SOURCE_BODY_AUDIT_RESULT:")
    print(json.dumps(result_block, ensure_ascii=False, indent=2))
    return summary


# ════════════════════════════════════════════════════════════════════════════
# Phase E-2 — full source revival (live orchestration loop)
# ════════════════════════════════════════════════════════════════════════════

# 사용자가 의도적으로 막은(우회 금지) 사유 → target에서 제외(§2.1).
_POLICY_EXCLUDE_REASONS = frozenset({
    "login_wall_no_bypass", "paywall_no_bypass", "robots_or_policy_block",
    "captcha_no_bypass", "disabled_by_policy", "user_excluded",
    "blocked_policy_no_bypass",
})
# 본문 fetch를 시도할 group(기사형). official/market/trend/search는 본문 fetch 불요.
_BODY_FETCH_GROUPS = frozenset({"news", "community"})


def _exclusion(profile) -> tuple[bool, Optional[str]]:
    """target 제외 여부 + 사유(§2.1). disabled 또는 정책 차단 skip_reason."""
    if not profile.enabled:
        return True, profile.skip_reason or "disabled"
    if profile.profile_status == "blocked_policy":
        return True, profile.skip_reason or "blocked_policy"
    if profile.skip_reason in _POLICY_EXCLUDE_REASONS:
        return True, profile.skip_reason
    return False, None


def _probe_artifact_candidates(probe_result, source_id: str, outputs_dir: Path) -> list[tuple[Path, Optional[str]]]:
    """live probe 직후 후보 artifact 경로들(+fmt). raw_payload/extracted_payload/raw_signal
    중 어느 것이 분해되는지는 소스마다 다르므로(예: HN raw=id리스트 vs extracted={items}),
    여기서는 후보만 모으고 선택은 _select_best_artifact가 분해 결과로 정한다."""
    ap = getattr(probe_result, "artifact_paths", None)
    out: list[tuple[Path, Optional[str]]] = []
    seen: set[str] = set()
    if ap is not None:
        for attr in ("raw_payload", "extracted_payload", "raw_signal", "raw_html"):
            v = getattr(ap, attr, None)
            if v and Path(v).is_file() and str(v) not in seen:
                seen.add(str(v))
                out.append((Path(v), _fmt_for(Path(v))))
    if not out:
        disk = _discover_artifact(source_id, outputs_dir)
        if disk is not None:
            out.append((disk, _fmt_for(disk)))
    return out


def _select_best_artifact(
    candidates: list[tuple[Path, Optional[str]]], *, source_id: str,
    confirmation_policy: Optional[str],
) -> tuple[Optional[str], Optional[Path], Optional[str]]:
    """후보 artifact 중 **가장 많이 분해되는 것**을 선택(0분해 회피, source-agnostic).

    모두 0분해면 첫 readable 후보를 반환(audit가 0분해 사유를 정직하게 기록하도록).
    """
    best: tuple[int, Optional[str], Optional[Path], Optional[str]] = (-1, None, None, None)
    first_readable: tuple[Optional[str], Optional[Path], Optional[str]] = (None, None, None)
    for path, fmt in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if first_readable[0] is None:
            first_readable = (text, path, fmt)
        try:
            cands, _parser, _errs = parse_artifact_text(
                text, source_id=source_id, confirmation_policy=confirmation_policy, fmt=fmt)
            n = len(cands)
        except Exception:
            n = 0
        if n > best[0]:
            best = (n, text, path, fmt)
    if best[0] > 0:
        return best[1], best[2], best[3]
    return first_readable


def _revive_one_source(
    profile, *, readiness, outputs_dir: Path, recorder: TraceRecorder,
    probe_fn, allow_body_fetch: bool, max_items: int,
) -> dict:
    """단일 소스 live revival: probe → audit → body fetch → structured signal →
    eventqueue readiness → final_status + root cause. 예외를 던지지 않는다(소스 격리)."""
    sid = profile.source_id
    grp = profile.source_group or "news"
    excluded, ex_reason = _exclusion(profile)
    rstat = readiness.readiness_status if readiness is not None else "not_required"
    key_ready = readiness.safe_to_live_smoke if readiness is not None else True

    plan = build_revival_plan(
        source_id=sid, source_group=grp, purpose=profile.purpose,
        enabled=profile.enabled, requires_api_key=profile.requires_api_key,
        api_key_ready=key_ready, excluded=excluded, excluded_reason=ex_reason,
    )
    recorder.record(sid, "profile_loaded", "ok", timestamp=_now_iso(),
                    metrics={"group": grp, "expected": plan.expected_alive_type})
    recorder.record(sid, "plan_created", "ok", timestamp=_now_iso(),
                    metrics={"excluded": excluded, "ladder_len": len(plan.strategy_ladder)})

    attempts: list[StrategyAttemptRecord] = []
    probe_status = "NOT_ATTEMPTED"
    artifact_path = None
    fmt = None
    text = None
    live_attempted = False

    # 제외 / 키 부재 → 호출하지 않고 정직하게 닫는다(no bypass).
    if excluded:
        recorder.record(sid, "source_not_alive", "warn", timestamp=_now_iso(),
                        message="excluded_by_policy", metrics={"reason": ex_reason})
    elif profile.requires_api_key and rstat == "missing":
        recorder.record(sid, "source_not_alive", "warn", timestamp=_now_iso(),
                        message="key_missing_no_call")
    else:
        # live orchestration call (run_collection_probe 경유, force=False, no bypass)
        live_attempted = True
        recorder.record(sid, "strategy_attempt_started", "ok", timestamp=_now_iso(),
                        metrics={"strategy": "collection_probe"})
        try:
            pr = probe_fn(sid, max_items=max_items, force=False)
            probe_status = pr.status
            cand_artifacts = _probe_artifact_candidates(pr, sid, outputs_dir)
            text, artifact_path, fmt = _select_best_artifact(
                cand_artifacts, source_id=sid,
                confirmation_policy=profile.confirmation_policy)
            if text is not None:
                recorder.record(sid, "artifact_saved", "ok", timestamp=_now_iso(),
                                metrics={"bytes": len(text),
                                         "selected": artifact_path.name if artifact_path else None})
            attempts.append(StrategyAttemptRecord(
                source_id=sid, strategy_name="collection_probe", attempt_index=0,
                attempted=True, status=("SUCCESS" if probe_status in ("LIVE_SUCCESS", "LIVE_PARTIAL")
                                        else probe_status),
                items_found=getattr(pr, "items_found", None), items_extracted=None,
                artifact_path=str(artifact_path) if artifact_path else None,
                candidate_count=0, body_present_count=0, structured_signal_count=0,
                eventqueue_ready_count=0,
                error_type=getattr(pr, "error_category", None), root_cause=None,
                next_strategy="artifact_parser",
            ))
            recorder.record(sid, "strategy_attempt_finished", "ok" if text else "warn",
                            timestamp=_now_iso(), metrics={"probe_status": probe_status})
        except Exception as exc:  # 소스 격리
            probe_status = "CYCLE_ERROR"
            recorder.record(sid, "source_failed", "error", timestamp=_now_iso(),
                            message="probe_exception",
                            metrics={"error_type": type(exc).__name__})

    # audit (parse/body/pre_gate) — text 없으면 no_artifact audit
    audit_result = audit_source_body(
        text, source_id=sid, purpose=profile.purpose, source_group=grp,
        confirmation_policy=profile.confirmation_policy,
        artifact_path=str(artifact_path) if artifact_path else None, fmt=fmt,
        recorder=recorder, timestamp=_now_iso(),
    )
    audit = audit_result.audit
    inspections = audit_result.inspections

    # body fetch (기사형 + snippet/missing + 첫 candidate URL이 있을 때만 1회)
    body_fetch = None
    fix_applied = None
    body_present = audit.body_present_count
    body_partial = audit.body_partial_count
    snippet_only = audit.snippet_only_count
    body_missing = audit.body_missing_count
    body_fetch_attempted = False
    body_fetch_excerpt = False
    if (allow_body_fetch and not excluded and grp in _BODY_FETCH_GROUPS
            and inspections and body_present == 0):
        first = inspections[0].candidate
        url = first.canonical_url or first.source_url
        recorder.record(sid, "body_fetch_started", "ok", timestamp=_now_iso(),
                        metrics={"has_url": bool(url)})
        # 본문 fetch는 기본 fetch_fn(html_fetch_tool/httpx) 사용. probe_fn은 1차 수집 전용.
        body_fetch = fetch_article_body(url, source_id=sid)
        body_fetch_attempted = body_fetch.attempted
        body_fetch_excerpt = body_fetch.excerpt_marker_detected
        recorder.record(sid, "body_fetch_finished",
                        "ok" if body_fetch.status == "SUCCESS" else "warn",
                        timestamp=_now_iso(),
                        metrics={"status": body_fetch.status,
                                 "body_length": body_fetch.body_length})
        if body_fetch.status == "SUCCESS":
            # 한 candidate의 본문이 실제로 확보됨 → 카운트 정직하게 1건 승격
            body_present += 1
            if snippet_only > 0:
                snippet_only -= 1
            elif body_missing > 0:
                body_missing -= 1
            fix_applied = "live_body_fetch_promoted_one_candidate"
            recorder.record(sid, "body_extracted", "ok", timestamp=_now_iso(),
                            metrics={"extractor": body_fetch.extractor_used})

    # structured signal 분리
    signals = to_structured_signal_candidates(
        [insp.candidate for insp in inspections], source_id=sid,
        source_group=grp, purpose=profile.purpose,
    )

    # eventqueue readiness (첫 candidate 기준 record 1건 + 분포)
    eq_records: list[dict] = []
    eq_ready = 0
    record_type = _record_type_for(grp)
    for insp in inspections[:max_items]:
        c = insp.candidate
        rec = build_eventqueue_record(
            record_type=record_type, source_id=sid,
            title_or_label=c.title, source_url_or_evidence=c.source_url or c.raw_artifact_path,
            canonical_url=c.canonical_url, published_at_or_observed_at=c.published_at,
            body_state_or_signal=insp.body_state.extraction_status,
            confirmation_policy=c.confirmation_policy,
            quality_pre_gate_decision=insp.pre_gate.decision,
        )
        ready, _gaps = check_eventqueue_readiness(rec)
        if ready:
            eq_ready += 1
        eq_records.append(rec)
    recorder.record(sid, "eventqueue_readiness_checked", "ok", timestamp=_now_iso(),
                    metrics={"records": len(eq_records), "ready": eq_ready})

    # final status + root cause
    evidence = RevivalEvidence(
        candidate_count=audit.candidate_count, title_present=audit.title_present_count,
        url_present=audit.url_present_count, published_present=audit.published_at_count,
        body_present=body_present, body_partial=body_partial,
        snippet_only=snippet_only, body_missing=body_missing,
        structured_signal=audit.structured_signal_count, parser_name=audit.parser_name,
        parser_gap_reason=audit.parser_gap_reason,
        body_fetch_attempted=body_fetch_attempted, body_fetch_excerpt=body_fetch_excerpt,
    )
    final_status, root_causes, next_action = classify_final_status(
        source_group=grp, excluded=excluded, excluded_reason=ex_reason,
        api_readiness_status=rstat, probe_status=probe_status,
        artifact_exists=audit.artifact_exists, evidence=evidence,
    )
    recorder.record(sid, "source_finalized",
                    "ok" if final_status.endswith("ALIVE") else "warn",
                    timestamp=_now_iso(),
                    metrics={"final_status": final_status, "root_causes": list(root_causes)})

    result = SourceRevivalResult(
        source_id=sid, source_group=grp, expected_alive_type=plan.expected_alive_type,
        final_status=final_status, root_causes=root_causes, next_action=next_action,
        fix_applied=fix_applied, attempts=tuple(attempts),
    )
    return {
        "plan": plan, "audit": audit, "inspections": inspections,
        "body_fetch": body_fetch, "signals": signals, "eq_records": eq_records,
        "eq_ready": eq_ready, "result": result, "live_attempted": live_attempted,
        "probe_status": probe_status, "excluded": excluded, "ex_reason": ex_reason,
        "body_counts": {"present": body_present, "partial": body_partial,
                        "snippet_only": snippet_only, "missing": body_missing},
    }


def _record_type_for(group: str) -> str:
    return {
        "news": "article_candidate", "community": "community_signal",
        "search": "search_result", "official": "official_record",
        "domain": "official_record", "market": "structured_signal",
        "trend": "structured_signal",
    }.get(group, "article_candidate")


def run_full_revival(args: argparse.Namespace) -> dict:
    """Phase E-2 live revival 루프. target 전부 live 시도 또는 policy-safe skip 후
    소스별 final_status를 확정한다. live 호출은 run_collection_probe 경유(no bypass)."""
    from ingestion.fetch_strategies.collection_probe import run_collection_probe
    from ingestion.orchestration.api_readiness import audit_api_key_readiness

    outputs_dir = _REPO_ROOT / "ingestion" / "outputs"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_root = Path(args.output_dir) / run_id
    out_root.mkdir(parents=True, exist_ok=True)
    recorder = TraceRecorder(run_id, jsonl_path=out_root / "trace.jsonl",
                             console=not args.no_console)

    profiles = load_source_profiles()
    if args.source:
        profiles = [p for p in profiles if p.source_id in args.source]
    readiness_list = audit_api_key_readiness(profiles)
    readiness_by_id = {r.source_id: r for r in readiness_list}

    target, excluded_profiles = [], []
    for p in profiles:
        (excluded_profiles if _exclusion(p)[0] else target).append(p)

    key_required_missing = sum(
        1 for p in target if p.requires_api_key
        and readiness_by_id.get(p.source_id)
        and readiness_by_id[p.source_id].readiness_status == "missing"
    )
    expected_live = len(target) - key_required_missing

    plan_block = {
        "run_id": run_id,
        "total_profiles": len(profiles),
        "target_sources": len(target),
        "excluded_sources": len(excluded_profiles),
        "expected_live_calls": expected_live,
        "key_missing_skipped": key_required_missing,
        "max_attempts_per_source": 4,
        "force": False,
        "max_items": args.max_items,
        "respect_rate_limit": True,
        "allow_network_body_fetch": bool(args.allow_network_body_fetch),
        "no_key_values_printed": True,
        "output_dir": str(out_root),
    }
    print("FULL_SOURCE_REVIVAL_PLAN:")
    print(json.dumps(plan_block, ensure_ascii=False, indent=2))
    (out_root / "plan.json").write_text(
        json.dumps(plan_block, ensure_ascii=False, indent=2), encoding="utf-8")

    samples_root = out_root / "samples"
    reports_root = out_root / "source_reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    eq_queue_path = outputs_dir / "jsonl" / "full_source_revival_event_queue.jsonl"
    eq_queue_path.parent.mkdir(parents=True, exist_ok=True)
    eq_preview_path = out_root / "event_queue_preview.jsonl"

    audits = []
    results: list[SourceRevivalResult] = []
    matrix_rows: list[dict] = []
    attempts_records: list[StrategyAttemptRecord] = []
    eq_record_type_dist: dict[str, int] = {}
    eq_written = 0

    # JSONL 큐는 REDIS_URL과 무관하게 명시 JSONL(빈 문자열)로 안전 처리.
    from ingestion.pipeline.event_queue import EventQueue
    audit_queue = EventQueue(redis_url="", fallback_dir=eq_queue_path.parent)
    # 별도 파일명을 위해 직접 append(기본 큐 파일을 건드리지 않는다).

    eq_lines: list[str] = []

    for p in profiles:
        one = _revive_one_source(
            p, readiness=readiness_by_id.get(p.source_id), outputs_dir=outputs_dir,
            recorder=recorder, probe_fn=run_collection_probe,
            allow_body_fetch=bool(args.allow_network_body_fetch),
            max_items=args.max_items,
        )
        audits.append(one["audit"])
        results.append(one["result"])
        attempts_records.extend(one["result"].attempts)

        # samples (gitignored)
        sample_saved = 0
        if args.save_samples and one["inspections"]:
            sample_saved = _write_samples(
                SourceBodyAuditResult(audit=one["audit"], inspections=one["inspections"]),
                samples_root, max_items=args.max_items, body_chars=args.sample_body_chars)

        # body fetch 증거 보존(F2): live fetch로 promote된 본문은 internal_only sample에만
        # sha256+길이+head를 남겨 ALIVE 판정을 사후 검증 가능하게 한다(전문은 미커밋).
        bf = one["body_fetch"]
        bf_status = bf.status if bf else None
        bf_len = bf.body_length if bf else 0
        bf_extractor = bf.extractor_used if bf else None
        bf_sha = None
        if bf and bf.status == "SUCCESS" and bf.body_text:
            bf_sha = hashlib.sha256(bf.body_text.encode("utf-8")).hexdigest()[:16]
            if args.save_samples:
                ev_dir = samples_root / p.source_id
                ev_dir.mkdir(parents=True, exist_ok=True)
                (ev_dir / "body_fetch_evidence.txt").write_text(
                    f"url: {bf.candidate_url}\nstatus: {bf.status}\n"
                    f"extractor: {bf.extractor_used}\nbody_length: {bf.body_length}\n"
                    f"sha256_16: {bf_sha}\nboilerplate_risk: {bf.boilerplate_risk}\n"
                    f"excerpt_marker: {bf.excerpt_marker_detected}\n\n"
                    f"--- body head (≤500 chars, internal_only) ---\n{bf.body_text[:500]}\n",
                    encoding="utf-8")

        # event queue records → audit queue file + preview
        for rec in one["eq_records"]:
            eq_lines.append(json.dumps(rec, ensure_ascii=False))
            eq_record_type_dist[rec["record_type"]] = eq_record_type_dist.get(rec["record_type"], 0) + 1
            eq_written += 1

        res = one["result"]
        bc = one["body_counts"]
        row = {
            "source_id": p.source_id, "source_group": res.source_group,
            "expected_alive_type": res.expected_alive_type,
            "final_status": res.final_status,
            "live_attempted": one["live_attempted"],
            "probe_status": one["probe_status"],
            "strategy_attempts": len(res.attempts),
            "artifact_exists": one["audit"].artifact_exists,
            "candidate_count": one["audit"].candidate_count,
            "body_present": bc["present"], "body_partial": bc["partial"],
            "snippet_only": bc["snippet_only"], "body_missing": bc["missing"],
            "structured_signal_count": one["audit"].structured_signal_count,
            "body_fetch_status": bf_status or "",
            "body_fetch_length": bf_len,
            "body_fetch_extractor": bf_extractor or "",
            "body_fetch_sha256_16": bf_sha or "",
            "eventqueue_ready_count": one["eq_ready"],
            "quality_pass": one["audit"].pre_gate_pass,
            "quality_hold": one["audit"].pre_gate_hold,
            "quality_reject": one["audit"].pre_gate_reject,
            "root_cause": ";".join(res.root_causes),
            "fix_applied": res.fix_applied or "",
            "next_action": res.next_action,
            "sample_saved": sample_saved,
        }
        matrix_rows.append(row)
        (reports_root / f"{p.source_id}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")

    # write audit event queue (별도 파일 — 기본 event_queue.jsonl 미접촉)
    if eq_lines:
        with eq_queue_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(eq_lines) + "\n")
        eq_preview_path.write_text("\n".join(eq_lines[:50]) + "\n", encoding="utf-8")

    # strategy_attempts.jsonl
    with (out_root / "strategy_attempts.jsonl").open("w", encoding="utf-8") as f:
        for a in attempts_records:
            f.write(json.dumps(asdict(a), ensure_ascii=False) + "\n")

    # source_matrix.csv / json
    (out_root / "source_matrix.json").write_text(
        json.dumps(matrix_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_root / "source_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(matrix_rows[0].keys()) if matrix_rows else [])
        w.writeheader()
        for r in matrix_rows:
            w.writerow(r)

    body_summary = summarize_body_audits(audits)
    revival_summary = summarize_revival(results)
    summary = {
        "run_id": run_id, "plan": plan_block,
        "body_audit": body_summary, "revival": revival_summary,
        "eventqueue": {"audit_queue_path": str(eq_queue_path),
                       "records_written": eq_written,
                       "record_type_distribution": eq_record_type_dist},
        "trace_stage_counts": recorder.stage_counts(),
    }
    (out_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    result_block = {
        "run_id": run_id,
        "target_sources": len(target),
        "excluded_sources": len(excluded_profiles),
        "final_status_distribution": revival_summary["final_status_distribution"],
        "root_cause_distribution": revival_summary["root_cause_distribution"],
        "alive": revival_summary["alive"],
        "data_alive": revival_summary["data_alive"],
        "fully_alive": revival_summary["fully_alive"],
        "degraded_alive": revival_summary["degraded_alive"],
        "degraded_sources": revival_summary["degraded_sources"],
        "unresolved": revival_summary["unresolved"],
        "unresolved_sources": revival_summary["unresolved_sources"],
        "complete_eligible": revival_summary["complete_eligible"],
        "body_present_total": body_summary["totals"]["body_present"],
        "snippet_only_total": body_summary["totals"]["snippet_only"],
        "structured_signal_total": body_summary["totals"]["structured_signal"],
        "eventqueue_records_written": eq_written,
        "verdict": ("FULL_SOURCE_REVIVAL_COMPLETE"
                    if revival_summary["complete_eligible"]
                    else "FULL_SOURCE_REVIVAL_PARTIAL"),
    }
    print("FULL_SOURCE_REVIVAL_RESULT:")
    print(json.dumps(result_block, ensure_ascii=False, indent=2))
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Phase E-1 replay audit / E-2 live full-source revival")
    ap.add_argument("--mode", default="audit", choices=["audit", "full-revival"],
                    help="audit=replay(E-1, network 0) / full-revival=live(E-2)")
    ap.add_argument("--scope", default="enabled",
                    choices=["enabled", "live_eligible", "all", "target"])
    ap.add_argument("--source", action="append", default=[],
                    help="특정 source_id만 (반복 가능)")
    ap.add_argument("--max-items", type=int, default=1)
    ap.add_argument("--output-dir",
                    default=str(_REPO_ROOT / "ingestion" / "outputs" / "tmp_source_body_audit"))
    ap.add_argument("--save-samples", action="store_true")
    ap.add_argument("--sample-body-chars", type=int, default=3000)
    ap.add_argument("--allow-network-body-fetch", action="store_true")
    ap.add_argument("--respect-rate-limit", default="true",
                    help="(full-revival) rate-limit 존중 — 항상 true(force=False 고정)")
    ap.add_argument("--no-console", action="store_true",
                    help="trace를 콘솔에 출력하지 않음(JSONL만)")
    args = ap.parse_args(argv)
    if args.mode == "full-revival":
        if args.output_dir.endswith("tmp_source_body_audit"):
            args.output_dir = str(
                _REPO_ROOT / "ingestion" / "outputs" / "tmp_full_source_revival")
        run_full_revival(args)
    else:
        run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
