"""2차 source(enrichment) live audit runner — docs/85 Step 5.

query set:
  A. hot seed — 1차 audit jsonl(--from-primary)에서 트렌드 keyword/뉴스 토픽/시장·도메인
     signal을 도출 (또는 --queries로 명시 주입).
  B. 대분류 — 한글 10종 + 영문 8종 상수.

소스별 query budget으로 샘플링 배정 (한글 query는 ko 미지원 소스에 배정하지 않음).
query 미지원 소스는 live 재호출 없이 audit_action="query_unsupported"로 기록하고
1차 결과를 참조해 enrichment 용도(파라미터형 lookup 등)를 평가한다.
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
from ingestion.core.rate_limit_policy import record_call
from ingestion.fetch_strategies.collection_probe import run_collection_probe
from ingestion.runners._audit_common import (
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    collect_samples,
    enforce_min_interval,
    evaluate_event_seed_fields,
    gate_check,
    relevance_label,
    relevance_score,
    safe_print,
    truncate_query,
    utc_now_iso,
    write_audit_jsonl,
    write_audit_md,
)

# B. 대분류 query 상수 (docs/85 Step 5)
CATEGORY_QUERIES_KO = [
    "정치", "국제 분쟁", "경제 위기", "주식 급등", "AI 반도체",
    "기후 재난", "문화 콘텐츠", "영화 박스오피스", "교통 사고", "공공 안전",
]
CATEGORY_QUERIES_EN = [
    "politics", "global conflict", "economic crisis", "stock surge",
    "AI semiconductor", "climate disaster", "box office", "public safety",
]

# 소스별 query budget (docs/85 호출 예산표)
_BUDGETS: list[tuple[str, int]] = [
    ("serper", 4), ("tavily", 4), ("exa", 4),
    ("naver_news_search", 4), ("naver_blog_search", 4),
    ("gnews", 2), ("newsapi", 2), ("guardian", 2), ("nyt", 2),
    ("gdelt", 2), ("sec_edgar", 2),
    ("youtube", 2), ("tmdb", 1),
]

_LANG_CAPS: dict[str, set] = {
    "naver_news_search": {"ko"}, "naver_blog_search": {"ko"},
    "exa": {"en"}, "gnews": {"en"}, "newsapi": {"en"}, "guardian": {"en"},
    "nyt": {"en"}, "gdelt": {"en"}, "sec_edgar": {"en"},
    "serper": {"ko", "en"}, "tavily": {"ko", "en"},
    "youtube": {"ko", "en"}, "tmdb": {"ko", "en"},
}

# query 미지원 — live 재호출 없이 1차 결과 참조 평가
_PARAMETERIZED_LOOKUP = [
    "opendart", "bok_ecos", "eia", "kma", "its", "tour", "kofic", "kopis",
    "aladin", "culture_info", "igdb",
    "finnhub", "twelve_data", "alpha_vantage", "polygon",
]
_FIXED_FEED = [
    "eu_press_corner", "hacker_news", "product_hunt",
    "coinbase_market", "binance_market",
    "signal_bz", "loword", "google_trending_now", "dcinside",
]

_RANK_PREFIX = re.compile(r"^\d+\s+")
_JUNK_TITLE_MARKERS = (
    "google trends", "로워드", "디시인사이드", "press corner",
    "지디넷", "전자신문", "associated press",
)
# 코드/심볼/날짜형 title은 query로 부적합 (kma 'PTY', twelve_data '2026-06-12' 등)
_JUNK_QUERY_PATTERNS = (
    re.compile(r"^\d{4}-\d{2}-\d{2}"),
    re.compile(r"^[A-Z]{2,6}$"),
    re.compile(r"^\d+$"),
)
# 시장/도메인 signal 그룹은 의미 있는 제목을 주는 소스만 사용
_SIGNAL_HOT_SOURCES = ("kofic", "opendart", "sec_edgar", "kopis", "aladin")


def _lang(query: str) -> str:
    return "ko" if re.search(r"[가-힣]", query) else "en"


def _clean_query(title: str, max_tokens: int = 5) -> str:
    t = re.sub(r"[\[\](){}'\"‘’“”…·,．/|:]", " ", title or "")
    tokens = [tok for tok in t.split() if len(tok) >= 2]
    cleaned = " ".join(tokens[:max_tokens])
    # RISK-Q05: 공백 없는 장문 토큰(opendart 공시명 등)은 토큰 상한으로 못 막으므로
    # 문자 상한까지 적용 — 규칙을 _audit_common.truncate_query로 단일화한다 (02 §3-d).
    return truncate_query(cleaned, max_tokens=max_tokens)


def derive_hot_queries(primary_jsonl: Path) -> list[dict]:
    """1차 audit jsonl에서 hot seed query 도출 (트렌드 3 + 뉴스 3 + 시장/도메인 2)."""
    records: list[dict] = []
    with primary_jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    def _usable_titles(layer: str) -> list[tuple[str, str]]:
        out = []
        for r in records:
            if r.get("layer") != layer or not r.get("samples"):
                continue
            for s in r["samples"]:
                title = (s.get("title") or "").strip()
                if not title:
                    continue
                if any(m in title.lower() for m in _JUNK_TITLE_MARKERS):
                    continue
                out.append((r["source_id"], title))
        return out

    hot: list[dict] = []

    def _add(source_id: str, title: str, origin: str, max_tokens: int = 5) -> None:
        q = _clean_query(_RANK_PREFIX.sub("", title), max_tokens)
        if len(q) < 2 or any(p.match(q) for p in _JUNK_QUERY_PATTERNS):
            return
        if all(h["query"] != q for h in hot):
            hot.append({"query": q, "origin": origin, "from_source": source_id})

    for sid, title in _usable_titles("fast_signal")[:3]:
        _add(sid, title, "fast_signal")
    for sid, title in _usable_titles("document_discovery"):
        if len([h for h in hot if h["origin"] == "document_discovery"]) >= 3:
            break
        _add(sid, title, "document_discovery")
    # 시장/공식/도메인 signal 2개 — 의미 있는 제목을 주는 소스 우선 (kofic 영화명 등)
    signal_added = 0
    for sid in _SIGNAL_HOT_SOURCES:
        if signal_added >= 2:
            break
        rec = next((r for r in records if r["source_id"] == sid and r.get("samples")), None)
        if not rec:
            continue
        title = (rec["samples"][0].get("title") or "").strip()
        if title:
            before = len(hot)
            _add(sid, title, rec.get("layer", "domain_signal"), max_tokens=3)
            if len(hot) > before:
                signal_added += 1
    return hot[:8]


def assign_queries(
    source_id: str, budget: int, hot: list[dict], categories: list[str], idx: int
) -> list[dict]:
    """budget 내에서 seed/대분류 query를 언어 호환 기준으로 배정 (결정적 round-robin)."""
    caps = _LANG_CAPS.get(source_id, {"ko", "en"})
    hot_pool = [h for h in hot if _lang(h["query"]) in caps]
    if source_id == "tmdb":
        # tmdb는 영화 제목 검색 — 도메인(박스오피스) 유래 seed 우선
        domain_hot = [h for h in hot_pool if h["origin"] == "domain_signal"]
        hot_pool = domain_hot or hot_pool
    cat_pool = [c for c in categories if _lang(c) in caps]

    seed_n = budget // 2
    cat_n = budget - seed_n
    if budget == 1 and hot_pool:
        seed_n, cat_n = 1, 0
    if not hot_pool:
        seed_n, cat_n = 0, budget

    assigned: list[dict] = []
    seen: set[str] = set()
    for i in range(seed_n):
        if not hot_pool:
            break
        h = hot_pool[(idx + i) % len(hot_pool)]
        if h["query"] not in seen:
            seen.add(h["query"])
            assigned.append({"query_type": "seed_based", **h})
    for i in range(cat_n):
        if not cat_pool:
            break
        q = cat_pool[(idx + i) % len(cat_pool)]
        if q not in seen:
            seen.add(q)
            assigned.append({"query_type": "category_based", "query": q,
                             "origin": "category", "from_source": None})
    return assigned


def audit_query_call(
    source_id: str,
    query_info: dict,
    max_items: int,
    respect_rate_limit: bool,
    dry_run: bool,
    last_called: dict,
) -> dict:
    query = query_info["query"]
    record: dict = {
        "source_id": source_id,
        "query_type": query_info["query_type"],
        "query": query,
        "query_origin": query_info.get("origin"),
        "query_from_source": query_info.get("from_source"),
        "audited_at": utc_now_iso(),
        "audit_action": "called",
        "status": None,
        "items_found": 0,
        "relevance": "unknown",
        "relevance_score": None,
        "samples": [],
        "minimum_fields_present": [],
        "error_category": None,
        "next_action": None,
        "elapsed_sec": 0.0,
    }
    if dry_run:
        record["audit_action"] = "dry_run"
        return record
    if respect_rate_limit:
        skip = gate_check(source_id, query)
        if skip:
            record["audit_action"] = skip
            record["next_action"] = "skipped_no_network_call"
            return record
        enforce_min_interval(source_id, last_called.get(source_id))

    t0 = time.monotonic()
    result = run_collection_probe(source_id, query=query, max_items=max_items)
    record["elapsed_sec"] = round(time.monotonic() - t0, 2)
    record_call(source_id, query)
    last_called[source_id] = time.monotonic()

    samples = collect_samples(result, max_items)
    best_count, best_fields = 0, []
    best_score = None
    for s in samples:
        item = dict(s)
        item["source_id"] = source_id
        count, fields = evaluate_event_seed_fields(item)
        if count > best_count:
            best_count, best_fields = count, fields
        score = relevance_score(query, s.get("title") or "", s.get("snippet") or "")
        if best_score is None or score > best_score:
            best_score = score

    record.update({
        "status": result.status,
        "items_found": max(result.items_found, len(samples)),
        "samples": samples,
        "minimum_fields_present": best_fields,
        "relevance": relevance_label(best_score) if best_score is not None else "unknown",
        "relevance_score": round(best_score, 3) if best_score is not None else None,
        "error_category": result.error_category,
        "next_action": result.next_action,
    })
    if record["items_found"] == 0 and result.status in ("LIVE_SUCCESS", "LIVE_PARTIAL"):
        record["next_action"] = "update_selector_or_query"
    return record


def unsupported_record(source_id: str, usage: str, primary_ref: Optional[dict]) -> dict:
    return {
        "source_id": source_id,
        "query_type": None,
        "query": None,
        "query_origin": None,
        "query_from_source": None,
        "audited_at": utc_now_iso(),
        "audit_action": "query_unsupported",
        "status": (primary_ref or {}).get("status"),
        "items_found": (primary_ref or {}).get("items_found", 0),
        "relevance": "unknown",
        "relevance_score": None,
        "samples": [],
        "minimum_fields_present": (primary_ref or {}).get("seed_field_coverage", []),
        "error_category": None,
        "next_action": "evaluate_from_primary_audit",
        "recommended_usage": usage,
        "elapsed_sec": 0.0,
    }


def _md_report(records: list[dict], ts: str) -> str:
    lines = [
        "# Enrichment Live Audit",
        "",
        f"- run: {ts} (UTC)",
        "",
        "| source_id | query_type | query | audit_action | status | items_found | relevance | minimum_fields_present | sample_title | sample_url_exists | published_at_exists | useful_for_expansion | recommended_usage | next_action |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        sample = r["samples"][0] if r["samples"] else {}
        title = (sample.get("title") or "-").replace("|", "\\|")[:70]
        useful = "yes" if (
            r["audit_action"] == "called"
            and r["status"] in ("LIVE_SUCCESS", "LIVE_PARTIAL")
            and r["items_found"] > 0
            and r["relevance"] in ("high", "medium")
        ) else ("lookup" if r["audit_action"] == "query_unsupported" else "no")
        usage = r.get("recommended_usage", "query_expansion")
        lines.append(
            f"| {r['source_id']} | {r['query_type'] or '-'} | {(r['query'] or '-')[:40]} "
            f"| {r['audit_action']} | {r['status'] or '-'} | {r['items_found']} "
            f"| {r['relevance']} | {','.join(r['minimum_fields_present']) or '-'} "
            f"| {title} | {'yes' if sample.get('url') else 'no'} "
            f"| {'yes' if sample.get('published_at') else 'no'} "
            f"| {useful} | {usage} | {r['next_action'] or '-'} |"
        )
    called = [r for r in records if r["audit_action"] == "called"]
    lines += [
        "",
        "## Summary",
        f"- live calls: {len(called)}",
        f"- relevance high: {len([r for r in called if r['relevance'] == 'high'])} "
        f"/ medium: {len([r for r in called if r['relevance'] == 'medium'])} "
        f"/ low: {len([r for r in called if r['relevance'] == 'low'])} "
        f"/ unknown: {len([r for r in called if r['relevance'] == 'unknown'])}",
        f"- skipped: {len([r for r in records if r['audit_action'] in ('cache_skip', 'cooldown_skip', 'health_skip')])}",
        f"- query_unsupported(참조 평가): {len([r for r in records if r['audit_action'] == 'query_unsupported'])}",
        "",
        "## Security Note",
        "API 키/토큰 값 없음. sample은 title 120자/snippet 200자 절단.",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Enrichment live audit (query budget)")
    parser.add_argument("--queries", nargs="*", default=None,
                        help="명시적 hot seed query (자동 도출 대체/보강)")
    parser.add_argument("--from-primary", default=None,
                        help="1차 audit jsonl 경로 — hot seed 자동 도출 + 미지원 소스 참조")
    parser.add_argument("--sources", nargs="*", default=None)
    parser.add_argument("--max-items", type=int, default=3)
    parser.add_argument("--respect-rate-limit", action="store_true", default=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    load_env()

    hot: list[dict] = []
    primary_index: dict[str, dict] = {}
    if args.from_primary:
        primary_path = Path(args.from_primary)
        hot = derive_hot_queries(primary_path)
        with primary_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    primary_index[rec["source_id"]] = rec
    if args.queries:
        for q in args.queries:
            if all(h["query"] != q for h in hot):
                hot.append({"query": q, "origin": "manual", "from_source": None})

    categories = CATEGORY_QUERIES_KO + CATEGORY_QUERIES_EN

    budgets = _BUDGETS
    if args.sources:
        wanted = set(args.sources)
        budgets = [(sid, b) for sid, b in budgets if sid in wanted]

    safe_print(f"hot seed queries ({len(hot)}): " + ", ".join(h["query"] for h in hot))

    records: list[dict] = []
    last_called: dict[str, float] = {}
    for idx, (sid, budget) in enumerate(budgets):
        assigned = assign_queries(sid, budget, hot, categories, idx)
        for qi in assigned:
            safe_print(f"[{sid}] ({qi['query_type']}) {qi['query']}")
            rec = audit_query_call(
                sid, qi, args.max_items, args.respect_rate_limit,
                args.dry_run, last_called,
            )
            records.append(rec)
            safe_print(
                f"    -> {rec['audit_action']} status={rec['status']} "
                f"items={rec['items_found']} relevance={rec['relevance']}"
            )

    if not args.sources:
        for sid in _PARAMETERIZED_LOOKUP:
            records.append(unsupported_record(
                sid, "parameterized_lookup_for_verification", primary_index.get(sid)))
        for sid in _FIXED_FEED:
            records.append(unsupported_record(
                sid, "periodic_seed_only", primary_index.get(sid)))

    ts = audit_timestamp()
    jsonl_path = write_audit_jsonl(records, OUTPUT_JSONL_DIR / f"enrichment_live_audit_{ts}.jsonl")
    md_path = write_audit_md(_md_report(records, ts), OUTPUT_REPORTS_DIR / f"enrichment_live_audit_{ts}.md")
    safe_print(f"jsonl : {jsonl_path}")
    safe_print(f"report: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
