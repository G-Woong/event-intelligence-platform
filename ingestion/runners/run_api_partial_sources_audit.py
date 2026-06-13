"""08 API partial/no 소스 E2E 종결 audit (docs/08 + docs/10 PHASE 4).

partial/no 였던 API 소스들이 실제로 sample을 만들고, event_candidate 또는 numeric_signal로
정제되며, URL 보유 소스는 본문 추출까지 시도되는지 end-to-end로 검증한다.

원인 분류(docs/08 §0):
  A 요청 필드 부족  B sample 매핑 부족  C seed_ready 기준 부적합(수치형)

대상:
  federal_register (A, event)  igdb (A, event)  culture_info (B, event)
  hacker_news (A, event/detail) bok_ecos·eia·its (B/C, numeric)  finnhub (C, numeric)

backend: 시작 시 INGESTION_RATE_LIMIT_BACKEND=local_file 강제(.env 미수정).
실패/키부재/쿨다운은 PASS가 아니라 collected=false + DEFERRED_NEEDS_KEY/NOT_CLOSED_*로 기록.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.core.artifact_store import new_run_id
from ingestion.core.env_loader import load_env
from ingestion.core.rate_limit_policy import in_cooldown, record_call
from ingestion.fetch_strategies.collection_probe import run_collection_probe
from ingestion.runners._audit_common import (
    NUMERIC_SIGNAL_SOURCES,
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    collect_samples,
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

# 대상 정의 — output_type/root_cause/body 여부
TARGETS: list[dict] = [
    {"id": "federal_register", "role": "primary_seed", "root_cause": "A",
     "output_type": "event_candidate", "body_required": True, "min_samples": 3},
    {"id": "igdb", "role": "domain_enrichment", "root_cause": "A",
     "output_type": "event_candidate", "body_required": False, "min_samples": 3},
    {"id": "culture_info", "role": "domain_enrichment", "root_cause": "B",
     "output_type": "event_candidate", "body_required": False, "min_samples": 3},
    {"id": "hacker_news", "role": "primary_seed", "root_cause": "A",
     "output_type": "event_candidate", "body_required": True, "min_samples": 3},
    {"id": "bok_ecos", "role": "numeric_signal", "root_cause": "B+C",
     "output_type": "numeric_signal", "body_required": False, "min_samples": 1},
    {"id": "eia", "role": "numeric_signal", "root_cause": "B+C",
     "output_type": "numeric_signal", "body_required": False, "min_samples": 1},
    {"id": "its", "role": "numeric_signal", "root_cause": "B+C",
     "output_type": "numeric_signal", "body_required": False, "min_samples": 1},
    {"id": "finnhub", "role": "numeric_signal", "root_cause": "C",
     "output_type": "numeric_signal", "body_required": False, "min_samples": 1},
]

_MAX_BODY_ATTEMPTS = 2
_BODY_FETCH_DELAY = 1.5


def _base_record(t: dict) -> dict:
    return {
        "run_id": None,
        "source_id": t["id"],
        "source_role": t["role"],
        "root_cause_A_B_C": t["root_cause"],
        "output_type": t["output_type"],
        "live_called": False,
        "collected": False,
        "samples_found": 0,
        "candidates_created": 0,
        "numeric_signals_created": 0,
        "body_extracted": 0,
        "body_status": "not_required" if not t["body_required"] else "pending",
        "body_artifact_path": None,
        "raw_artifact_path": None,
        "status": None,
        "error_category": None,
        "next_retry_at": None,
        "next_action": None,
        "samples": [],
        "audited_at": utc_now_iso(),
        "final_status": None,
    }


def _build_numeric_signal(source_id: str, sample: dict) -> dict:
    """sample → numeric_signal record (metric_name/value/date/source). 억지 article 변환 안 함."""
    return {
        "source_id": source_id,
        "metric_name": sample.get("title"),
        "value": sample.get("snippet"),
        "observed_at": sample.get("published_at"),
        "collected_at": utc_now_iso(),
    }


def _flat_numeric_signal(source_id: str, raw_path: Optional[str]) -> list[dict]:
    """flat quote 응답(list 아님, finnhub {c,h,l,o,pc} 등)에서 단일 numeric_signal 구성.

    list 추출이 안 되는 수치 소스의 정직한 처리 — 데이터 수신 자체가 signal이므로
    scalar 숫자 필드를 metrics로 묶어 1건 기록한다 (억지 article 변환 안 함).
    """
    import json
    if not raw_path or not Path(raw_path).exists():
        return []
    try:
        parsed = json.loads(Path(raw_path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    if not isinstance(parsed, dict):
        return []
    metrics = {k: v for k, v in parsed.items() if isinstance(v, (int, float))}
    if not metrics:
        return []
    return [{
        "source_id": source_id,
        "metric_name": f"{source_id}_quote",
        "metrics": metrics,
        "collected_at": utc_now_iso(),
    }]


def audit_source(t: dict, *, max_items: int, respect_rate_limit: bool) -> dict:
    sid = t["id"]
    rec = _base_record(t)

    if respect_rate_limit:
        skip = gate_check(sid, "")
        if skip:
            rec["status"] = skip.upper()
            if skip == "cooldown_skip":
                _c, at = in_cooldown(sid, "")
                rec["next_retry_at"] = at
                rec["final_status"] = "NOT_CLOSED_EXTERNAL_RATE_LIMIT"
            else:
                rec["final_status"] = "NOT_CLOSED_GATE_SKIP"
            rec["next_action"] = "retry_after_gate_window"
            return rec

    run_id = new_run_id(1, sid)
    rec["run_id"] = run_id
    rec["live_called"] = True
    t0 = time.monotonic()
    result = run_collection_probe(sid, max_items=max_items)
    rec["elapsed_sec"] = round(time.monotonic() - t0, 2)
    record_call(sid, "")

    status = result.status
    raw_path = (result.artifact_paths.raw_payload or result.artifact_paths.raw_html
                or result.artifact_paths.extracted_payload)
    next_retry = result.probe_result.next_retry_at if result.probe_result else None
    rec.update({"status": status, "error_category": result.error_category,
                "raw_artifact_path": raw_path, "next_retry_at": next_retry})

    # 키 부재 — PASS 아님 (DEFERRED_NEEDS_KEY)
    if status == "MISSING_KEY":
        rec["final_status"] = "DEFERRED_NEEDS_KEY"
        rec["next_action"] = "add_api_key_to_.env"
        return rec
    if status == "RATE_LIMITED":
        rec["final_status"] = "NOT_CLOSED_EXTERNAL_RATE_LIMIT"
        rec["next_action"] = "retry_after_cooldown"
        return rec
    if status == "BLOCKED":
        rec["final_status"] = "BLOCKED_TERMINAL"
        rec["next_action"] = "see_compliance_boundary"
        return rec

    samples = collect_samples(result, max_items)
    rec["samples_found"] = len(samples)
    rec["samples"] = samples[:3]

    if t["output_type"] == "numeric_signal":
        signals = [_build_numeric_signal(sid, s) for s in samples if s.get("title")]
        # list가 없는 flat quote 소스(finnhub 등): 데이터 수신 자체가 signal_ready
        if not signals and result.items_found > 0:
            signals = _flat_numeric_signal(sid, raw_path)
        rec["numeric_signals_created"] = len(signals)
        rec["collected"] = len(signals) > 0
        rec["final_status"] = "PASS" if len(signals) >= t["min_samples"] else "NOT_CLOSED_NO_SAMPLES"
        rec["next_action"] = "closed" if rec["final_status"] == "PASS" else "inspect_mapping"
        return rec

    # event_candidate
    candidates = [s for s in samples if s.get("title")]
    rec["candidates_created"] = len(candidates)
    rec["collected"] = len(candidates) > 0

    body_attempted = 0
    if t["body_required"] and candidates:
        for cand in candidates:
            if body_attempted >= _MAX_BODY_ATTEMPTS:
                break
            url = cand.get("url")
            if not (url and str(url).startswith("http")):
                continue
            if body_attempted > 0:
                time.sleep(_BODY_FETCH_DELAY)
            body_attempted += 1
            b = extract_body(sid, cand, fetch_fn=_default_fetch_html)
            rec["body_status"] = b["body_status"]
            if b["body_status"] == "extracted":
                rec["body_extracted"] += 1
                rec["body_artifact_path"] = b["body_artifact_path"]
                break

    enough = len(candidates) >= t["min_samples"]
    if not enough:
        rec["final_status"] = "NOT_CLOSED_NO_CANDIDATES" if candidates else "NOT_CLOSED_NO_SAMPLES"
        rec["next_action"] = "inspect_mapping_or_fields"
    elif t["body_required"] and body_attempted == 0:
        rec["final_status"] = "NOT_CLOSED_BODY_NOT_ATTEMPTED"
        rec["next_action"] = "no_http_url_in_candidates"
    else:
        rec["final_status"] = "PASS"
        rec["next_action"] = "closed"
    return rec


def _md_report(records: list[dict], ts: str) -> str:
    lines = [
        "# API Partial Sources E2E Audit (docs/08)",
        "",
        f"- run: {ts} (UTC)",
        f"- sources: {len(records)}",
        "",
        "| source_id | root_cause | output_type | live | collected | samples | candidates | numeric | body | status | final_status | next_action |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['source_id']} | {r['root_cause_A_B_C']} | {r['output_type']} "
            f"| {'y' if r['live_called'] else 'n'} | {'y' if r['collected'] else 'n'} "
            f"| {r['samples_found']} | {r['candidates_created']} | {r['numeric_signals_created']} "
            f"| {r['body_extracted']}/{r['body_status']} | {r['status'] or '-'} "
            f"| {r['final_status']} | {r['next_action'] or '-'} |"
        )
    passed = [r for r in records if r["final_status"] == "PASS"]
    lines += [
        "",
        "## Summary",
        f"- PASS: {len(passed)} / {len(records)}",
        f"- candidates total: {sum(r['candidates_created'] for r in records)}",
        f"- numeric_signals total: {sum(r['numeric_signals_created'] for r in records)}",
        f"- body_extracted total: {sum(r['body_extracted'] for r in records)}",
        f"- DEFERRED_NEEDS_KEY: {len([r for r in records if r['final_status'] == 'DEFERRED_NEEDS_KEY'])}",
        "",
        "## Security Note",
        "API 키/토큰 값 없음. sample은 title 120자/snippet 200자 절단.",
    ]
    return "\n".join(lines)


def run_audit(sources: Optional[list[str]], max_items: int,
              respect_rate_limit: bool) -> list[dict]:
    force_local_file_backend()
    load_env()
    targets = TARGETS
    if sources:
        wanted = set(sources)
        targets = [t for t in TARGETS if t["id"] in wanted]
    records: list[dict] = []
    for i, t in enumerate(targets, 1):
        safe_print(f"[{i}/{len(targets)}] {t['id']} ({t['output_type']}) ...")
        rec = audit_source(t, max_items=max_items, respect_rate_limit=respect_rate_limit)
        records.append(rec)
        safe_print(
            f"    -> {rec['final_status']} status={rec['status']} "
            f"samples={rec['samples_found']} cand={rec['candidates_created']} "
            f"num={rec['numeric_signals_created']} body={rec['body_extracted']}"
        )
    return records


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="08 API partial sources E2E audit")
    parser.add_argument("--sources", nargs="*", default=None)
    parser.add_argument("--max-items", type=int, default=3)
    parser.add_argument("--no-rate-limit", action="store_true",
                        help="gate_check 건너뜀 (테스트/디버그용)")
    args = parser.parse_args(argv)

    records = run_audit(args.sources, args.max_items, respect_rate_limit=not args.no_rate_limit)
    ts = audit_timestamp()
    jsonl = write_audit_jsonl(records, OUTPUT_JSONL_DIR / f"api_partial_sources_e2e_audit_{ts}.jsonl")
    md = write_audit_md(_md_report(records, ts), OUTPUT_REPORTS_DIR / f"api_partial_sources_e2e_audit_{ts}.md")
    safe_print(f"jsonl : {jsonl}")
    safe_print(f"report: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
