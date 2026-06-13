"""07 — Playwright/selector 소스 5종 E2E audit.

실제 수집 → event candidate 생성 → candidate JSONL 누적 → (가능 시) 본문 추출
artifact 저장까지 end-to-end로 검증한다. 실패/쿨다운은 PASS가 아니라
collected=false + status로 정직하게 기록한다 (page title fallback 성공 처리 금지).

backend는 INGESTION_RATE_LIMIT_BACKEND=local_file 강제 — 429 cooldown이
rate_limit_cache.json에 영속되어 다음 호출을 gate가 차단(연속 재시도 방지).

대상:
  signal_bz             trend_keyword   (≥10 candidates + rank)
  google_trending_now   trend_keyword   (≥3)
  loword                trend_keyword    (≥3)
  dcinside              community_post   (query 검색 ≥3 + body ≥1)
  eu_press_corner       press_release    (≥3, 가능 시 본문 1+)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.probes.playwright_probe import run_playwright_probe
from ingestion.runners._audit_common import (
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    gate_check,
    safe_print,
    utc_now_iso,
)

_RATE_LIMIT_BACKEND = "local_file"

# (source_id, candidate_type, query, region, min_candidates, body_required)
E2E_TARGETS: list[dict] = [
    {"source_id": "signal_bz", "candidate_type": "trend_keyword",
     "query": None, "region": None, "min_candidates": 10, "body_required": False},
    {"source_id": "google_trending_now", "candidate_type": "trend_keyword",
     "query": None, "region": "KR", "min_candidates": 3, "body_required": False},
    {"source_id": "loword", "candidate_type": "trend_keyword",
     "query": None, "region": None, "min_candidates": 3, "body_required": False},
    {"source_id": "dcinside", "candidate_type": "community_post",
     "query": "삼성전자", "region": None, "min_candidates": 3, "body_required": True},
    {"source_id": "eu_press_corner", "candidate_type": "press_release",
     "query": None, "region": None, "min_candidates": 3, "body_required": False},
]


def force_local_file_backend() -> str:
    import os
    from ingestion.core.rate_limit_store import reset_store_for_tests
    os.environ["INGESTION_RATE_LIMIT_BACKEND"] = _RATE_LIMIT_BACKEND
    reset_store_for_tests()
    from ingestion.core.rate_limit_store import get_store
    return type(get_store()).__name__


def _load_items(raw_signal_path: Optional[str]) -> list[dict]:
    if not raw_signal_path or not Path(raw_signal_path).exists():
        return []
    try:
        return json.loads(Path(raw_signal_path).read_text(encoding="utf-8"))
    except Exception:
        return []


def _body_artifacts(artifact_paths: dict) -> list[str]:
    return [str(v) for k, v in (artifact_paths or {}).items()
            if k.startswith("extracted_body_")]


def _read_body_meta(path: str) -> tuple[str, int, Optional[str]]:
    """save_extracted_payload JSON → (extraction_method, body_length, title)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return (data.get("method", ""), len(data.get("body") or ""), data.get("title"))
    except Exception:
        return ("", 0, None)


def _final_status(target: dict, probe_status: str, candidates: int,
                  body_extracted: int, gate_skip: Optional[str]) -> str:
    if gate_skip == "cooldown_skip":
        return "DEFERRED_EXTERNAL_RATE_LIMIT"
    if gate_skip == "health_skip":
        return "DEFERRED_EXTERNAL_RATE_LIMIT"
    if probe_status == "RATE_LIMITED":
        return "DEFERRED_EXTERNAL_RATE_LIMIT"
    if probe_status == "BLOCKED":
        return "BLOCKED_TERMINAL"
    if candidates < target["min_candidates"]:
        return "IN_LOOP_SELECTOR"
    if target["body_required"] and body_extracted < 1:
        return "IN_LOOP_BODY_EXTRACTION"
    return "PASS"


def audit_source(target: dict, respect_rate_limit: bool = True) -> dict:
    sid = target["source_id"]
    query = target["query"]
    record: dict = {
        "run_id": audit_timestamp(),
        "source_id": sid,
        "candidate_type": target["candidate_type"],
        "query": query,
        "collected": False,
        "items_found": 0,
        "candidates_created": 0,
        "body_required": target["body_required"],
        "body_extracted": 0,
        "candidates": [],
        "status": "PENDING",
        "error_category": None,
        "next_retry_at": None,
        "raw_artifact_path": None,
        "screenshot_path": None,
        "rendered_dom_path": None,
        "observed_at": utc_now_iso(),
    }

    gate_skip = gate_check(sid, query or "") if respect_rate_limit else None
    if gate_skip in ("cooldown_skip", "health_skip"):
        record["status"] = _final_status(target, "GATE_SKIP", 0, 0, gate_skip)
        record["error_category"] = gate_skip
        record["next_action"] = "retry_after_cooldown_or_health_recovery"
        return record

    probe = run_playwright_probe(
        sid, query=query, region=target["region"], max_items=20,
    )
    ap = probe.artifact_paths or {}
    record["items_found"] = probe.items_found
    record["raw_artifact_path"] = ap.get("raw_signal")
    record["screenshot_path"] = ap.get("screenshot")
    record["rendered_dom_path"] = ap.get("rendered_dom")
    record["next_retry_at"] = probe.next_retry_at
    record["error_category"] = probe.error_category

    items = _load_items(ap.get("raw_signal"))
    body_paths = _body_artifacts(ap)
    body_meta_by_index: dict = {}
    for i, bp in enumerate(body_paths):
        method, blen, btitle = _read_body_meta(bp)
        body_meta_by_index[i] = {"path": bp, "method": method, "length": blen, "title": btitle}

    candidates: list[dict] = []
    for i, it in enumerate(items):
        cand = {
            "source_id": sid,
            "candidate_type": target["candidate_type"],
            "title_or_keyword": it.get("keyword"),
            "url": it.get("url") or None,
            "canonical_url": it.get("url") or None,
            "rank": it.get("rank"),
            "observed_at": record["observed_at"],
            "published_at": None,
            "body_status": "not_required" if not target["body_required"] else "pending",
            "body_length": 0,
            "body_artifact_path": None,
            "extraction_method": None,
            "evidence_level": "low",
            "status": "collected",
        }
        # body artifact를 url 일치 또는 순서로 연결
        if i in body_meta_by_index:
            bm = body_meta_by_index[i]
            cand["body_status"] = "extracted"
            cand["body_length"] = bm["length"]
            cand["body_artifact_path"] = bm["path"]
            cand["extraction_method"] = bm["method"]
        candidates.append(cand)

    body_extracted = sum(1 for c in candidates if c["body_status"] == "extracted")
    record["candidates"] = candidates
    record["candidates_created"] = len(candidates)
    record["body_extracted"] = body_extracted
    record["collected"] = len(candidates) > 0
    record["status"] = _final_status(
        target, probe.status, len(candidates), body_extracted, gate_skip)
    record["probe_status"] = probe.status
    record["next_action"] = probe.next_action
    return record


def run_audit(targets: list[dict], respect_rate_limit: bool = True) -> list[dict]:
    return [audit_source(t, respect_rate_limit) for t in targets]


def _render_md(records: list[dict]) -> str:
    lines = ["# Playwright/selector sources E2E audit", "",
             "| source_id | status | collected | items | candidates | body | next_retry |",
             "|---|---|---|---|---|---|---|"]
    for r in records:
        lines.append(
            f"| {r['source_id']} | {r['status']} | {r['collected']} | "
            f"{r['items_found']} | {r['candidates_created']} | {r['body_extracted']} | "
            f"{r.get('next_retry_at') or '-'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Playwright/selector sources E2E audit.")
    parser.add_argument("--sources", default=None,
                        help="comma-separated source_ids (default: all 5)")
    parser.add_argument("--no-rate-limit", action="store_true",
                        help="bypass gate (force live call regardless of cooldown)")
    args = parser.parse_args(argv)

    backend = force_local_file_backend()
    safe_print(f"rate-limit backend forced: {backend}")

    targets = E2E_TARGETS
    if args.sources:
        wanted = {s.strip() for s in args.sources.split(",")}
        targets = [t for t in E2E_TARGETS if t["source_id"] in wanted]

    records = run_audit(targets, respect_rate_limit=not args.no_rate_limit)

    ts = audit_timestamp()
    jsonl_path = OUTPUT_JSONL_DIR / f"playwright_selector_sources_e2e_audit_{ts}.jsonl"
    md_path = OUTPUT_REPORTS_DIR / f"playwright_selector_sources_e2e_audit_{ts}.md"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_render_md(records), encoding="utf-8")

    for r in records:
        safe_print(f"[{r['source_id']}] status={r['status']} collected={r['collected']} "
                   f"items={r['items_found']} candidates={r['candidates_created']} "
                   f"body={r['body_extracted']}")
    safe_print(f"jsonl: {jsonl_path}")
    safe_print(f"report: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
