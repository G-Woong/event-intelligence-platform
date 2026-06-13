"""1차 source(seed 감지) live audit runner — docs/85 Step 4.

소스당 1회 원칙. gate_check(health→cooldown→cache) → min_interval 강제 →
run_collection_probe → record_call → sample ≤3 추출 → seed 필드 평가.
skip은 record의 audit_action으로만 기록 (네트워크 호출 없음).
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

from ingestion.core.env_loader import load_env
from ingestion.core.rate_limit_policy import cache_key, record_call
from ingestion.core.rate_limit_store import get_store
from ingestion.fetch_strategies.collection_probe import run_collection_probe
from ingestion.runners._audit_common import (
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    collect_samples,
    enforce_min_interval,
    evaluate_event_seed_fields,
    extract_samples_from_rendered,
    gate_check,
    load_audit_sources,
    safe_print,
    seed_ready_label,
    utc_now_iso,
    write_audit_jsonl,
    write_audit_md,
)

# 1차 audit는 검색 enrichment layer 제외 (2차 runner 담당)
_DEFAULT_LAYERS = [
    "document_discovery", "community_signal", "official_evidence",
    "fast_signal", "market_signal", "domain_signal",
]

# 보고서 recommended_frequency 초안 (docs/86 기준 — docs/92에서 확정)
_FREQ_OVERRIDES = {
    "alpha_vantage": "daily(quota 25/day)",
    "kofic": "daily",
    "polygon": "daily",
    "google_trending_now": "2h+(429 이력)",
    "eu_press_corner": "2-6h",
    "federal_register": "daily",
    "bok_ecos": "daily", "eia": "daily", "kopis": "daily",
    "aladin": "daily", "igdb": "daily-weekly", "tour": "weekly",
    "product_hunt": "daily", "tmdb": "daily",
    "finnhub": "5-15m", "binance_market": "5-15m",
    "yna": "15-30m", "gdelt": "15-30m",
}
_FREQ_BY_LAYER = {
    "document_discovery": "30-60m",
    "community_signal": "30-60m",
    "official_evidence": "30-60m",
    "fast_signal": "30-60m",
    "market_signal": "15-30m",
    "domain_signal": "daily",
}


def _evaluate_seed(source_id: str, samples: list[dict]) -> tuple[str, list[str]]:
    """sample 중 최고 필드 충족 기준으로 seed_ready 판정."""
    best_count, best_fields = 0, []
    for s in samples:
        item = dict(s)
        item["source_id"] = source_id
        count, fields = evaluate_event_seed_fields(item)
        if count > best_count:
            best_count, best_fields = count, fields
    return seed_ready_label(best_count), best_fields


def audit_one_source(
    source: dict,
    max_items: int = 3,
    respect_rate_limit: bool = True,
    dry_run: bool = False,
) -> dict:
    sid = source["id"]
    record: dict = {
        "source_id": sid,
        "layer": source.get("layer", ""),
        "audited_at": utc_now_iso(),
        "audit_action": "called",
        "status": None,
        "strategy_used": None,
        "items_found": 0,
        "samples": [],
        "seed_ready": "no",
        "seed_field_coverage": [],
        "error_category": None,
        "next_action": None,
        "elapsed_sec": 0.0,
    }

    if dry_run:
        record["audit_action"] = "dry_run"
        record["next_action"] = "run_without_dry_run"
        return record

    if respect_rate_limit:
        skip = gate_check(sid, "")
        if skip:
            record["audit_action"] = skip
            record["next_action"] = "skipped_no_network_call"
            return record
        age = get_store().age_seconds(cache_key(sid, ""))
        last_called = (time.monotonic() - age) if age is not None else None
        enforce_min_interval(sid, last_called)

    t0 = time.monotonic()
    result = run_collection_probe(sid, max_items=max_items)
    record["elapsed_sec"] = round(time.monotonic() - t0, 2)
    record_call(sid, "")

    samples = collect_samples(result, max_items)
    seed_ready, coverage = _evaluate_seed(sid, samples)

    items_found = result.items_found
    if samples and len(samples) > items_found:
        items_found = len(samples)

    record.update({
        "status": result.status,
        "strategy_used": result.strategy_used,
        "items_found": items_found,
        "samples": samples,
        "seed_ready": seed_ready,
        "seed_field_coverage": coverage,
        "error_category": result.error_category,
        "next_action": result.next_action,
        "artifact_exists": bool(
            result.artifact_paths.raw_payload or result.artifact_paths.raw_html
            or (result.extraction and result.extraction.rendered_page
                and result.extraction.rendered_page.rendered_dom_path)
        ),
    })
    if items_found == 0 and result.status in ("LIVE_SUCCESS", "LIVE_PARTIAL"):
        record["next_action"] = "update_selector"
    return record


def audit_trends_explore(respect_rate_limit: bool = True) -> dict:
    """google_trends_explore — opt-in 전용 (429 이력). gate 통과 시 ≤1회."""
    sid = "google_trends_explore"
    record = {
        "source_id": sid, "layer": "fast_signal", "audited_at": utc_now_iso(),
        "audit_action": "called", "status": None, "strategy_used": "playwright",
        "items_found": 0, "samples": [], "seed_ready": "no",
        "seed_field_coverage": [], "error_category": None,
        "next_action": None, "elapsed_sec": 0.0,
    }
    if respect_rate_limit:
        skip = gate_check(sid, "")
        if skip:
            record["audit_action"] = skip
            record["next_action"] = "skipped_no_network_call"
            return record
    try:
        from ingestion.probes.site_specs import load_site_specs
        spec = load_site_specs().get(sid)
        url = spec.start_url.format(query="news", region="US") if spec else ""
        if not url:
            record["status"] = "UNKNOWN"
            record["next_action"] = "no_site_spec"
            return record
        from ingestion.fetch_strategies.cloud_browser_like import CloudBrowserLikeStrategy
        t0 = time.monotonic()
        rendered = CloudBrowserLikeStrategy().fetch(url, sid)
        record["elapsed_sec"] = round(time.monotonic() - t0, 2)
        record_call(sid, "")
        samples = extract_samples_from_rendered(sid, rendered.html, 3)
        record["status"] = rendered.status
        record["samples"] = samples
        record["items_found"] = len(samples)
        seed_ready, coverage = _evaluate_seed(sid, samples)
        record["seed_ready"] = seed_ready
        record["seed_field_coverage"] = coverage
        record["error_category"] = (
            rendered.error_category.value if rendered.error_category else None
        )
        record["next_action"] = (
            "enrichment_only_source" if rendered.status == "LIVE_SUCCESS"
            else "respect_cooldown_no_retry"
        )
    except Exception as exc:
        record["status"] = "UNKNOWN"
        record["error_category"] = type(exc).__name__
        record["next_action"] = "investigate"
    return record


def _md_report(records: list[dict], ts: str) -> str:
    lines = [
        "# Primary Seed Live Audit",
        "",
        f"- run: {ts} (UTC)",
        f"- sources: {len(records)}",
        "",
        "| source_id | layer | audit_action | status | items_found | event_seed_ready | minimum_fields_present | sample_title_or_keyword | sample_url_exists | timestamp_exists | artifact_exists | recommended_frequency | next_action |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        sample = r["samples"][0] if r["samples"] else {}
        title = (sample.get("title") or "-").replace("|", "\\|")[:80]
        freq = _FREQ_OVERRIDES.get(
            r["source_id"], _FREQ_BY_LAYER.get(r["layer"], "UNKNOWN"))
        lines.append(
            f"| {r['source_id']} | {r['layer']} | {r['audit_action']} | {r['status'] or '-'} "
            f"| {r['items_found']} | {r['seed_ready']} | {','.join(r['seed_field_coverage']) or '-'} "
            f"| {title} | {'yes' if sample.get('url') else 'no'} "
            f"| {'yes' if sample.get('published_at') else 'no'} "
            f"| {'yes' if r.get('artifact_exists') else 'no'} | {freq} | {r['next_action'] or '-'} |"
        )
    called = [r for r in records if r["audit_action"] == "called"]
    ready = [r for r in called if r["seed_ready"] == "yes"]
    lines += [
        "",
        "## Summary",
        f"- called: {len(called)} / skipped: {len(records) - len(called)}",
        f"- seed_ready(yes): {len(ready)}",
        f"- seed_ready(partial): {len([r for r in called if r['seed_ready'] == 'partial'])}",
        f"- LIVE_SUCCESS: {len([r for r in called if r['status'] == 'LIVE_SUCCESS'])}",
        "",
        "## Security Note",
        "API 키/토큰 값 없음. sample은 title 120자/snippet 200자 절단.",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Primary seed live audit (1 call/source)")
    parser.add_argument("--layers", nargs="*", default=None,
                        help=f"기본: {_DEFAULT_LAYERS}")
    parser.add_argument("--sources", nargs="*", default=None)
    parser.add_argument("--max-items", type=int, default=3)
    parser.add_argument("--respect-rate-limit", action="store_true", default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-trends-explore", action="store_true", default=False)
    args = parser.parse_args(argv)

    load_env()

    layers = args.layers if args.layers else _DEFAULT_LAYERS
    sources = load_audit_sources(layers=layers)
    if args.sources:
        wanted = set(args.sources)
        sources = [s for s in sources if s["id"] in wanted]

    records: list[dict] = []
    for i, source in enumerate(sources, 1):
        safe_print(f"[{i}/{len(sources)}] {source['id']} ...")
        rec = audit_one_source(
            source, max_items=args.max_items,
            respect_rate_limit=args.respect_rate_limit, dry_run=args.dry_run,
        )
        records.append(rec)
        safe_print(
            f"    -> {rec['audit_action']} status={rec['status']} "
            f"items={rec['items_found']} seed={rec['seed_ready']}"
        )

    if args.include_trends_explore and not args.dry_run:
        safe_print("[extra] google_trends_explore (opt-in, gate 선확인)")
        rec = audit_trends_explore(respect_rate_limit=args.respect_rate_limit)
        records.append(rec)
        safe_print(f"    -> {rec['audit_action']} status={rec['status']}")

    ts = audit_timestamp()
    jsonl_path = write_audit_jsonl(records, OUTPUT_JSONL_DIR / f"primary_seed_live_audit_{ts}.jsonl")
    md_path = write_audit_md(_md_report(records, ts), OUTPUT_REPORTS_DIR / f"primary_seed_live_audit_{ts}.md")
    safe_print(f"jsonl : {jsonl_path}")
    safe_print(f"report: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
