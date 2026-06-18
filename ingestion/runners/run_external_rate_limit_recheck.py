"""외부 rate-limit 소스 재검증 audit (docs/10 PHASE 3-4).

gdelt(API+query)와 google_trends_explore(Playwright)가 정말 provider rate limit인지,
아니면 정책 주기 이후 정상 수집이 가능한지 실제 호출로 재검증한다.

원칙(하드 제약):
  · 소스당 live 호출 최대 1회, 연속 재시도 금지.
  · gate_check(health→cooldown→cache) 통과 시에만 호출.
  · 게이트가 쿨다운이면 재호출하지 않고, 최근 산출 artifact를 근거로 정직하게 분류한다
    (gdelt: 직전 성공 artifact가 있으면 수집 능력 PASS / 없으면 NOT_CLOSED).
  · INGESTION_RATE_LIMIT_BACKEND=local_file 강제(.env 미수정).

분류(final_classification):
  PASS                       — 실제 JSON/관련검색어 수집 + (gdelt) 본문 추출 성공
  RATE_LIMITED_CONFIRMED     — 429/soft-limit 재현(rendered_dom·응답 근거 + next_retry 영속)
  NOT_CLOSED_NO_EVIDENCE     — 쿨다운인데 근거 artifact도 없음(재시도 필요)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.core.env_loader import load_env
from ingestion.core.error_taxonomy import is_rate_limited_text
from ingestion.core.rate_limit_policy import in_cooldown, record_call
from ingestion.fetch_strategies.collection_probe import run_collection_probe
from ingestion.runners._audit_common import (
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    collect_samples,
    extract_sample_items,
    gate_check,
    safe_print,
    utc_now_iso,
    write_audit_jsonl,
    write_audit_md,
)
from ingestion.runners.run_conditional_sources_e2e_audit import (
    _default_fetch_html,
    extract_body,
    force_local_file_backend,
)

_OUT_ROOT = _REPO_ROOT / "ingestion" / "outputs"


def _newest(glob_dir: Path, pattern: str) -> Optional[Path]:
    if not glob_dir.exists():
        return None
    files = sorted(glob_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _content_type_of(raw_path: Optional[str]) -> Optional[str]:
    if not raw_path or not Path(raw_path).exists():
        return None
    head = Path(raw_path).read_text(encoding="utf-8", errors="replace").lstrip()[:1]
    if head in ("{", "["):
        return "application/json"
    if head == "<":
        return "text/html_or_xml"
    return "text/plain"


def _base_row(sid: str, method: str) -> dict:
    cd, at = in_cooldown(sid, "")
    return {
        "source_id": sid,
        "method": method,
        "cooldown_before": cd,
        "cooldown_before_next_retry_at": at,
        "query": None,
        "region": None,
        "live_called": False,
        "response_status": None,
        "content_type": None,
        "samples_found": 0,
        "candidates_created": 0,
        "body_extracted": 0,
        "body_status": None,
        "body_artifact_path": None,
        "raw_artifact_path": None,
        "rendered_dom": None,
        "screenshot": None,
        "next_retry_at": at,
        "evidence_refs": [],
        "final_classification": None,
        "next_action": None,
        "audited_at": utc_now_iso(),
    }


def recheck_gdelt(query: str, max_items: int = 3) -> dict:
    row = _base_row("gdelt", "api")
    row["query"] = query
    skip = gate_check("gdelt", query)
    # cooldown_skip 또는 rate-limit 기인 health_skip(직전 429로 인한 cooldown) 모두
    # 재호출하지 않고 직전 성공 artifact로 판정한다 (둘 다 외부 rate limit 신호).
    rate_limit_skip = skip == "cooldown_skip"
    if skip == "health_skip":
        from ingestion.core.source_health import get_health_store
        rec = get_health_store().get("gdelt")
        if rec and "rate_limited" in (getattr(rec, "reason", "") or ""):
            rate_limit_skip = True
            row["next_retry_at"] = getattr(rec, "next_retry_at", None)
    if rate_limit_skip:
        # 재호출하지 않는다 — 직전 성공 artifact로 수집 능력을 판정한다.
        art = _newest(_OUT_ROOT / "extracted_payload" / "gdelt", "*.json")
        if art:
            samples = extract_sample_items("gdelt", str(art), max_items)
            cand = [s for s in samples if s.get("title")]
            row.update({
                "response_status": "COOLDOWN_USED_PRIOR_ARTIFACT",
                "content_type": "application/json",
                "samples_found": len(samples),
                "candidates_created": len(cand),
                "raw_artifact_path": str(art),
                "evidence_refs": [str(art)],
            })
            # 본문 추출은 article URL(aif.ru 등)을 호출 — GDELT rate-limit과 무관하므로 시도 가능.
            for c in cand:
                url = c.get("url")
                if not (url and str(url).startswith("http")):
                    continue
                b = extract_body("gdelt", c, fetch_fn=_default_fetch_html)
                row["body_status"] = b["body_status"]
                if b["body_status"] == "extracted":
                    row["body_extracted"] = 1
                    row["body_artifact_path"] = b["body_artifact_path"]
                    break
            row["final_classification"] = "PASS" if len(cand) >= 3 else "NOT_CLOSED_NO_EVIDENCE"
            row["next_action"] = ("respect_cooldown_collection_proven" if len(cand) >= 3
                                  else "wait_cooldown_then_recall")
        else:
            row.update({
                "response_status": "COOLDOWN_NO_ARTIFACT",
                "final_classification": "NOT_CLOSED_NO_EVIDENCE",
                "next_action": "wait_cooldown_then_recall",
            })
        return row
    if skip:
        row["response_status"] = skip.upper()
        row["final_classification"] = "NOT_CLOSED_NO_EVIDENCE"
        row["next_action"] = "retry_after_gate_window"
        return row

    # 게이트 열림 — 실제 1회 호출
    row["live_called"] = True
    res = run_collection_probe("gdelt", query=query, max_items=max_items)
    record_call("gdelt", query)
    raw = (res.artifact_paths.raw_payload or res.artifact_paths.raw_html
           or getattr(res.artifact_paths, "extracted_payload", None))
    row.update({
        "response_status": res.status,
        "content_type": _content_type_of(raw),
        "raw_artifact_path": raw,
    })
    samples = collect_samples(res, max_items)
    cand = [s for s in samples if s.get("title")]
    row["samples_found"] = len(samples)
    row["candidates_created"] = len(cand)

    # soft-limit: 200인데 본문이 rate-limit 평문 → CONFIRMED
    soft_limited = False
    if raw and Path(raw).exists():
        soft_limited = is_rate_limited_text(
            Path(raw).read_text(encoding="utf-8", errors="replace")[:2000])
    if res.status == "RATE_LIMITED" or soft_limited:
        cd, at = in_cooldown("gdelt", query)
        row["next_retry_at"] = at
        row["final_classification"] = "RATE_LIMITED_CONFIRMED"
        row["next_action"] = "retry_after_cooldown"
        return row

    # 본문 추출 1회 시도
    if cand:
        for c in cand:
            url = c.get("url")
            if not (url and str(url).startswith("http")):
                continue
            b = extract_body("gdelt", c, fetch_fn=_default_fetch_html)
            row["body_status"] = b["body_status"]
            if b["body_status"] == "extracted":
                row["body_extracted"] = 1
                row["body_artifact_path"] = b["body_artifact_path"]
                break
    row["final_classification"] = "PASS" if len(cand) >= 3 else "NOT_CLOSED_NO_SAMPLES"
    row["next_action"] = "closed" if len(cand) >= 3 else "inspect_mapping"
    return row


def recheck_trends(query: str, region: str = "US") -> dict:
    row = _base_row("google_trends_explore", "playwright")
    row["query"] = query
    row["region"] = region
    skip = gate_check("google_trends_explore", query)
    if skip == "cooldown_skip":
        # 재호출 금지 — 직전 429 rendered_dom 근거로 CONFIRMED.
        dom = _newest(_OUT_ROOT / "rendered_dom" / "google_trends_explore", "*.html")
        ss = _newest(_OUT_ROOT / "screenshots" / "google_trends_explore", "*.png")
        cd, at = in_cooldown("google_trends_explore", query)
        confirmed = False
        if dom:
            confirmed = is_rate_limited_text(
                dom.read_text(encoding="utf-8", errors="replace"))
        row.update({
            "response_status": "COOLDOWN_RATE_LIMITED",
            "rendered_dom": str(dom) if dom else None,
            "screenshot": str(ss) if ss else None,
            "next_retry_at": at,
            "evidence_refs": [p for p in (str(dom) if dom else None, str(ss) if ss else None) if p],
            "final_classification": "RATE_LIMITED_CONFIRMED" if confirmed else "NOT_CLOSED_NO_EVIDENCE",
            "next_action": "respect_cooldown_no_retry",
        })
        return row
    if skip:
        row["response_status"] = skip.upper()
        row["final_classification"] = "NOT_CLOSED_NO_EVIDENCE"
        row["next_action"] = "retry_after_gate_window"
        return row

    # 게이트 열림 — 실제 1회 호출
    row["live_called"] = True
    from ingestion.probes.playwright_probe import run_playwright_probe
    res = run_playwright_probe("google_trends_explore", query=query, region=region, max_items=10)
    ap = res.artifact_paths or {}
    row.update({
        "response_status": res.status,
        "rendered_dom": ap.get("rendered_dom"),
        "screenshot": ap.get("screenshot"),
        "samples_found": res.items_found,
    })
    if res.status == "RATE_LIMITED":
        row.update({
            "next_retry_at": res.next_retry_at,
            "evidence_refs": [p for p in (ap.get("rendered_dom"), ap.get("screenshot")) if p],
            "final_classification": "RATE_LIMITED_CONFIRMED",
            "next_action": "respect_cooldown_no_retry",
        })
    elif res.status in ("LIVE_SUCCESS", "LIVE_PARTIAL") and res.items_found >= 3:
        row.update({
            "candidates_created": res.items_found,
            "body_status": "not_required",
            "final_classification": "PASS",
            "next_action": "enrichment_only_source",
        })
    else:
        row.update({
            "final_classification": "NOT_CLOSED_NO_EVIDENCE",
            "next_action": "run_structure_explorer_for_selectors",
        })
    return row


def _md_report(rows: list[dict], ts: str) -> str:
    lines = [
        "# External Rate-Limit Recheck (docs/10 PHASE 3-4)",
        "",
        f"- run: {ts} (UTC)",
        "",
        "| source_id | method | live | response_status | content_type | samples | candidates | body | next_retry_at | final_classification |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['source_id']} | {r['method']} | {'y' if r['live_called'] else 'n'} "
            f"| {r['response_status'] or '-'} | {r['content_type'] or '-'} "
            f"| {r['samples_found']} | {r['candidates_created']} "
            f"| {r['body_extracted']}/{r['body_status'] or '-'} | {r['next_retry_at'] or '-'} "
            f"| {r['final_classification']} |"
        )
    lines += [
        "",
        "## Security Note",
        "API 키/토큰 값 없음. 외부 provider 재호출은 소스당 ≤1회, 쿨다운 시 재호출 금지.",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="External rate-limit recheck (gdelt, google_trends_explore)")
    parser.add_argument("--gdelt-query", default="global conflict")
    parser.add_argument("--trends-query", default="samsung")
    parser.add_argument("--trends-region", default="US")
    parser.add_argument("--max-items", type=int, default=3)
    args = parser.parse_args(argv)

    force_local_file_backend()
    load_env()

    rows: list[dict] = []
    safe_print("[1/2] gdelt recheck ...")
    g = recheck_gdelt(args.gdelt_query, args.max_items)
    rows.append(g)
    safe_print(f"    -> {g['final_classification']} status={g['response_status']} "
               f"cand={g['candidates_created']} body={g['body_extracted']}")

    safe_print("[2/2] google_trends_explore recheck ...")
    t = recheck_trends(args.trends_query, args.trends_region)
    rows.append(t)
    safe_print(f"    -> {t['final_classification']} status={t['response_status']} "
               f"items={t['samples_found']}")

    ts = audit_timestamp()
    jsonl = write_audit_jsonl(rows, OUTPUT_JSONL_DIR / f"external_rate_limit_recheck_{ts}.jsonl")
    md = write_audit_md(_md_report(rows, ts), OUTPUT_REPORTS_DIR / f"external_rate_limit_recheck_{ts}.md")
    safe_print(f"jsonl : {jsonl}")
    safe_print(f"report: {md}")
    return 0


if __name__ == "__main__":
    print(
        "[DEPRECATED] This runner is a one-shot legacy audit (docs/10 PHASE 3-4).\n"
        "Canonical orchestration: python -m ingestion.tools.run_production_orchestration\n"
        "No-call source validation: python -m ingestion.tools.run_orchestration_source_validation",
        file=sys.stderr,
    )
    sys.exit(main())
