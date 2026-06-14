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


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Phase E-1 per-source body extraction audit")
    ap.add_argument("--scope", default="enabled",
                    choices=["enabled", "live_eligible", "all"])
    ap.add_argument("--source", action="append", default=[],
                    help="특정 source_id만 (반복 가능)")
    ap.add_argument("--max-items", type=int, default=1)
    ap.add_argument("--output-dir",
                    default=str(_REPO_ROOT / "ingestion" / "outputs" / "tmp_source_body_audit"))
    ap.add_argument("--save-samples", action="store_true")
    ap.add_argument("--sample-body-chars", type=int, default=3000)
    ap.add_argument("--allow-network-body-fetch", action="store_true")
    ap.add_argument("--no-console", action="store_true",
                    help="trace를 콘솔에 출력하지 않음(JSONL만)")
    args = ap.parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
