"""Google Trends fallback enrichment audit (PHASE 2 / 4).

google_trends_explore가 provider 429로 막혀도 "트렌드 seed / related expansion" 재료가
계속 확보되는지 안전·합법 대체 경로로 검증한다. 우회(CAPTCHA/로그인/proxy/RPC)는 하지 않는다.

fallback chain:
  A. google_trending_now (이미 PASS된 Playwright seed source) — trend item ≥3 + event candidate.
     cooldown이면 재호출하지 않고 직전 raw_signal artifact로 평가.
  B. Google Trends Trending Now export(RSS) 탐색 — feed_discovery로 공개 RSS endpoint 검증.
     찾으면 items 추출, 못 찾으면 EXPORT_UNAVAILABLE(=BLOCKED 아님, A를 primary로 유지).
  C. 뉴스/검색 enrichment fallback — hot seed 1개를 serper/tavily/exa/naver/gnews/newsapi/
     guardian/ap_news에 질의하고 title+snippet에서 규칙 기반 related_candidate를 생성.
     URL 결과가 있으면 본문 추출 ≥1회 시도.

추가로 google_trends_explore의 cooldown/429 상태를 재호출 없이 1 row로 기록한다(optional
source failure가 event queue 전체를 막지 않음을 입증).

성공 기준(PHASE 2): explore가 429여도 related_candidate ≥5, collected fallback source ≥2,
본문 추출 시도 ≥1, 실패/blocked/rate-limited source도 JSONL에서 누락하지 않음.
"""
from __future__ import annotations

import argparse
import json
import re
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
    extract_related_candidates,
    extract_sample_items,
    gate_check,
    safe_print,
    truncate_query,
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
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_RANK_PREFIX = re.compile(r"^\d+[\.\)\s]+")

# Stage C: (source_id, 허용 query 언어) — 한글 query는 ko 미포함 소스에 보내지 않는다.
_STAGE_C_SOURCES: list[tuple[str, set]] = [
    ("serper", {"ko", "en"}),
    ("tavily", {"ko", "en"}),
    ("naver_news_search", {"ko"}),
    ("exa", {"en"}),
    ("gnews", {"en"}),
    ("newsapi", {"en"}),
    ("guardian", {"en"}),
    ("ap_news", {"en"}),  # Google News RSS 프록시 (합법 공개 RSS)
]

# Stage B: 공개 Trending Now RSS export 후보 (Google 내부 RPC/batchexecute 아님)
_EXPORT_CANDIDATES: list[tuple[str, str]] = [
    ("trending_now_rss", "https://trends.google.com/trending/rss?geo={region}"),
    ("daily_trends_rss", "https://trends.google.com/trends/trendingsearches/daily/rss?geo={region}"),
]


def _lang(q: str) -> str:
    return "ko" if re.search(r"[가-힣]", q or "") else "en"


def _clean_seed(title: str) -> str:
    t = _RANK_PREFIX.sub("", (title or "").strip())
    t = re.sub(r"[\[\](){}'\"‘’“”…·|]", " ", t)
    return truncate_query(t, max_tokens=4, max_chars=40)


def _newest(glob_dir: Path, pattern: str) -> Optional[Path]:
    if not glob_dir.exists():
        return None
    files = sorted(glob_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _base_row(run_id: str, seed: Optional[str], source_id: str, stage: str) -> dict:
    return {
        "run_id": run_id,
        "seed_keyword": seed,
        "source_id": source_id,
        "fallback_stage": stage,
        "collected": False,
        "items_found": 0,
        "candidates_created": 0,
        "related_candidates_created": 0,
        "related_candidates": [],
        "body_extracted": 0,
        "body_status": None,
        "body_artifact_path": None,
        "status": None,
        "error_category": None,
        "artifact_path": None,
        "evidence_refs": [],
        "next_action": None,
        "audited_at": utc_now_iso(),
    }


# ── Stage A: google_trending_now ─────────────────────────────────────────────

def stage_a(run_id: str, max_items: int, respect: bool, dry_run: bool) -> tuple[dict, list[str]]:
    sid = "google_trending_now"
    row = _base_row(run_id, None, sid, "google_trending_now")
    if dry_run:
        row["status"] = "DRY_RUN"
        return row, []
    skip = gate_check(sid, "") if respect else None
    if skip:
        art = _newest(_OUT_ROOT / "raw_signal" / sid, "*.json")
        samples = extract_sample_items(sid, str(art), max_items) if art else []
        seeds = [_clean_seed(s.get("title") or "") for s in samples]
        seeds = [s for s in seeds if len(s) >= 2]
        row.update({
            "status": "COOLDOWN_USED_PRIOR_ARTIFACT" if art else skip.upper(),
            "collected": bool(samples),
            "items_found": len(samples),
            "candidates_created": len(samples),
            "artifact_path": str(art) if art else None,
            "evidence_refs": [str(art)] if art else [],
            "next_action": ("seed_from_prior_artifact" if samples
                            else "wait_gate_then_recall"),
        })
        return row, seeds

    res = run_collection_probe(sid, max_items=max_items)
    record_call(sid, "")
    samples = collect_samples(res, max_items)
    seeds = [_clean_seed(s.get("title") or "") for s in samples]
    seeds = [s for s in seeds if len(s) >= 2]
    raw = res.artifact_paths.raw_payload or res.artifact_paths.raw_html
    row.update({
        "status": res.status,
        "collected": bool(samples),
        "items_found": max(res.items_found, len(samples)),
        "candidates_created": len(samples),
        "artifact_path": raw,
        "error_category": res.error_category,
        "next_action": "trend_seed_ready" if samples else "update_selector",
    })
    return row, seeds


# ── Stage B: Trending Now RSS export 탐색 ────────────────────────────────────

def _fetch_rss_entries(url: str, max_items: int) -> Optional[list[dict]]:
    """공개 RSS GET → feedparser. 유효(bozo==0 & entries)면 entry 목록, 아니면 None."""
    try:
        import feedparser
        import httpx
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _BROWSER_UA})
        if resp.status_code != 200:
            return None
        parsed = feedparser.parse(resp.content)
        if getattr(parsed, "bozo", 1) != 0 or not parsed.entries:
            return None
        out = []
        for e in parsed.entries[:max_items]:
            out.append({"title": (getattr(e, "title", "") or "").strip(),
                        "link": getattr(e, "link", "") or ""})
        return out
    except Exception:
        return None


def stage_b(run_id: str, region: str, max_items: int, dry_run: bool) -> tuple[dict, list[str]]:
    sid = "google_trends_trending_now_export"
    row = _base_row(run_id, None, sid, "trends_export")
    if dry_run:
        row["status"] = "DRY_RUN"
        return row, []
    tried: list[dict] = []
    for name, tmpl in _EXPORT_CANDIDATES:
        url = tmpl.format(region=region)
        entries = _fetch_rss_entries(url, max_items)
        ok = bool(entries)
        tried.append({"endpoint": name, "url": url, "valid_feed": ok})
        if ok:
            out_dir = _OUT_ROOT / "raw_payload" / sid
            out_dir.mkdir(parents=True, exist_ok=True)
            art = out_dir / f"{audit_timestamp()}_{name}.json"
            art.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            seeds = [_clean_seed(e["title"]) for e in entries if e.get("title")]
            seeds = [s for s in seeds if len(s) >= 2]
            row.update({
                "status": "EXPORT_AVAILABLE",
                "collected": True,
                "items_found": len(entries),
                "candidates_created": len(entries),
                "artifact_path": str(art),
                "evidence_refs": [url],
                "next_action": "onboard_as_registry_source_next_round",
            })
            return row, seeds
    row.update({
        "status": "EXPORT_UNAVAILABLE",
        "collected": False,
        "evidence_refs": [t["url"] for t in tried],
        "error_category": "EXPORT_PATH_NOT_FOUND",
        "next_action": "use_google_trending_now_playwright_as_primary",
    })
    return row, []


# ── Stage C: 뉴스/검색 enrichment fallback ───────────────────────────────────

def stage_c(
    run_id: str, seed: str, max_items: int, respect: bool, dry_run: bool,
    sources_filter: Optional[set], body_budget: int = 3,
) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    all_related: list[dict] = []
    related_seen: set = set()
    seed_lang = _lang(seed)
    body_attempts = 0
    body_done = False

    for sid, caps in _STAGE_C_SOURCES:
        if sources_filter and sid not in sources_filter:
            continue
        row = _base_row(run_id, seed, sid, "news_search")
        if dry_run:
            row["status"] = "DRY_RUN"
            rows.append(row)
            continue
        if seed_lang not in caps:
            row.update({"status": "LANG_SKIP", "next_action": "seed_language_unsupported"})
            rows.append(row)
            continue
        if respect:
            skip = gate_check(sid, seed)
            if skip:
                row.update({"status": skip.upper(), "next_action": "skipped_no_network_call"})
                rows.append(row)
                continue

        res = run_collection_probe(sid, query=seed, max_items=max_items)
        record_call(sid, seed)
        samples = collect_samples(res, max_items)
        related = extract_related_candidates(seed, samples)
        fresh = [r for r in related if r["phrase"].lower() not in related_seen]
        for r in fresh:
            related_seen.add(r["phrase"].lower())
        all_related.extend(fresh)

        raw = res.artifact_paths.raw_payload or res.artifact_paths.raw_html
        row.update({
            "status": res.status,
            "collected": bool(samples),
            "items_found": max(res.items_found, len(samples)),
            "candidates_created": len(samples),
            "related_candidates_created": len(related),
            "related_candidates": related[:8],
            "artifact_path": raw,
            "error_category": res.error_category,
            "next_action": "related_expansion_ready" if related else "no_related_extracted",
        })

        # 본문 추출 ≥1회 시도 (stage C 전체에서 1건 성공할 때까지, budget 내)
        if not body_done and body_attempts < body_budget:
            for s in samples:
                url = s.get("url")
                if not (url and str(url).startswith("http")):
                    continue
                body_attempts += 1
                b = extract_body(sid, s, fetch_fn=_default_fetch_html)
                row["body_status"] = b["body_status"]
                if b["body_status"] == "extracted":
                    row["body_extracted"] = 1
                    row["body_artifact_path"] = b["body_artifact_path"]
                    body_done = True
                break
        rows.append(row)
    return rows, all_related


# ── google_trends_explore cooldown/429 상태 (재호출 없음) ────────────────────

def explore_status_row(run_id: str, seed: str) -> dict:
    sid = "google_trends_explore"
    row = _base_row(run_id, seed, sid, "explore_optional")
    row["body_status"] = "not_required"
    skip = gate_check(sid, seed)
    dom = _newest(_OUT_ROOT / "rendered_dom" / sid, "*.html")
    confirmed = False
    if dom:
        confirmed = is_rate_limited_text(dom.read_text(encoding="utf-8", errors="replace"))
    cd, at = in_cooldown(sid, seed)
    if skip == "cooldown_skip" or cd or confirmed:
        # query-keyed cooldown이 없어도, 직전 rendered_dom이 정품 429면 IP 단위
        # confirmed external rate limit이므로 재호출하지 않고 그대로 기록한다.
        row.update({
            "status": "RATE_LIMITED_CONFIRMED" if confirmed else "COOLDOWN_ACTIVE",
            "collected": False,
            "artifact_path": str(dom) if dom else None,
            "evidence_refs": [str(dom)] if dom else [],
            "next_action": "optional_enrichment_failed_use_fallback_chain",
        })
    elif skip:
        row.update({"status": skip.upper(), "collected": False,
                    "next_action": "optional_enrichment_skipped_use_fallback_chain"})
    else:
        # 게이트 열림이지만 confirmed external rate limit → 재호출하지 않고 정직 기록
        row.update({
            "status": "GATE_OPEN_NOT_RECALLED",
            "collected": False,
            "artifact_path": str(dom) if dom else None,
            "next_action": "optional_recall_one_shot_outside_audit",
        })
    return row


def _md_report(rows: list[dict], related_total: int, ts: str) -> str:
    lines = [
        "# Trend Fallback Enrichment Audit (PHASE 2/4)",
        "",
        f"- run: {ts} (UTC)",
        f"- aggregate related_candidates: {related_total}",
        "",
        "| stage | source_id | collected | items | candidates | related | body | status | next_action |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['fallback_stage']} | {r['source_id']} | {'y' if r['collected'] else 'n'} "
            f"| {r['items_found']} | {r['candidates_created']} | {r['related_candidates_created']} "
            f"| {r['body_extracted']}/{r['body_status'] or '-'} | {r['status'] or '-'} "
            f"| {r['next_action'] or '-'} |"
        )
    collected = [r for r in rows if r["collected"]]
    lines += [
        "",
        "## Summary",
        f"- collected sources: {len(collected)} / {len(rows)}",
        f"- aggregate related_candidates: {related_total}",
        f"- body_extracted: {sum(r['body_extracted'] for r in rows)}",
        "",
        "## Security Note",
        "API 키/토큰 값 없음. 우회(CAPTCHA/로그인/proxy/RPC) 없음. 공개 RSS/검색 API만 사용.",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Google Trends fallback enrichment audit (A:trending_now B:export C:news/search)"
    )
    parser.add_argument("--seed", default=None, help="명시 hot seed (기본: stage A 트렌드 1위)")
    parser.add_argument("--region", default="KR")
    parser.add_argument("--max-items", type=int, default=3)
    parser.add_argument("--sources", nargs="*", default=None, help="stage C 소스 부분집합")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--respect-rate-limit", action="store_true", default=True)
    args = parser.parse_args(argv)

    force_local_file_backend()
    load_env()

    ts = audit_timestamp()
    run_id = f"trendfb_{ts}"
    rows: list[dict] = []

    safe_print("[A] google_trending_now ...")
    a_row, a_seeds = stage_a(run_id, args.max_items, args.respect_rate_limit, args.dry_run)
    rows.append(a_row)
    safe_print(f"    -> {a_row['status']} collected={a_row['collected']} seeds={a_seeds[:5]}")

    safe_print("[B] trends export discovery ...")
    b_row, b_seeds = stage_b(run_id, args.region, args.max_items, args.dry_run)
    rows.append(b_row)
    safe_print(f"    -> {b_row['status']} collected={b_row['collected']}")

    seed = args.seed or (a_seeds[0] if a_seeds else None) or (b_seeds[0] if b_seeds else None) \
        or "global conflict"
    safe_print(f"[C] news/search enrichment fallback — seed='{seed}'")
    sources_filter = set(args.sources) if args.sources else None
    c_rows, related = stage_c(
        run_id, seed, args.max_items, args.respect_rate_limit, args.dry_run, sources_filter
    )
    rows.extend(c_rows)
    for r in c_rows:
        safe_print(f"    [{r['source_id']}] {r['status']} collected={r['collected']} "
                   f"related={r['related_candidates_created']}")

    safe_print("[explore] google_trends_explore status (no recall) ...")
    e_row = explore_status_row(run_id, seed)
    rows.append(e_row)
    safe_print(f"    -> {e_row['status']}")

    related_total = len(related)
    safe_print(f"aggregate related_candidates: {related_total}")

    jsonl = write_audit_jsonl(rows, OUTPUT_JSONL_DIR / f"trend_fallback_enrichment_audit_{ts}.jsonl")
    md = write_audit_md(_md_report(rows, related_total, ts),
                        OUTPUT_REPORTS_DIR / f"trend_fallback_enrichment_audit_{ts}.md")
    safe_print(f"jsonl : {jsonl}")
    safe_print(f"report: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
