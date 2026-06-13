from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def normalize_api_result(service_id: str, parsed: Any) -> dict:
    """Extract meaningful fields from a parsed API JSON response."""
    if not isinstance(parsed, dict):
        return {"raw_type": type(parsed).__name__, "length": len(parsed) if hasattr(parsed, "__len__") else 0}

    _FIELD_MAP: dict[str, list[str]] = {
        "naver_news_search": ["items", "total", "display"],
        "naver_blog_search": ["items", "total", "display"],
        "youtube": ["items", "pageInfo", "kind"],
        "gdelt": ["articles"],
        "sec_edgar": ["hits", "total"],
        "federal_register": ["results", "count", "total_pages"],
        "hacker_news": [],
        "opendart": ["list", "total_count", "status"],
        "eia": ["routes"],
        "bok_ecos": ["StatisticTableList"],
        "product_hunt": ["data"],
        "reddit": ["data"],
        "coinbase_market": ["products"],
        "binance_market": [],
        "hacker_news": [],
    }

    field_names = _FIELD_MAP.get(service_id, list(parsed.keys())[:5])
    return {k: parsed[k] for k in field_names if k in parsed}


def normalize_signal_items(site_id: str, items: list) -> list[dict]:
    """Normalize trend keyword items to canonical signal schema."""
    observed_at = datetime.now(timezone.utc).isoformat()
    result: list[dict] = []
    for i, item in enumerate(items):
        if isinstance(item, str):
            result.append({
                "source": site_id,
                "signal_type": "trending_keyword",
                "official": False,
                "evidence_level": "low",
                "rank": i + 1,
                "keyword": item,
                "observed_at": observed_at,
                "source_url": "",
                "collection_method": "playwright",
            })
        elif isinstance(item, dict):
            result.append({
                "source": site_id,
                "signal_type": item.get("signal_type", "trending_keyword"),
                "official": item.get("official", False),
                "evidence_level": item.get("evidence_level", "low"),
                "rank": item.get("rank", i + 1),
                "keyword": item.get("keyword") or item.get("text") or "",
                "observed_at": item.get("observed_at", observed_at),
                "source_url": item.get("source_url", ""),
                "collection_method": item.get("collection_method", "playwright"),
            })
    return result


def normalize_doc_items(site_id: str, items: list) -> list[dict]:
    """Normalize community document items to canonical doc schema."""
    result: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        result.append({
            "source": site_id,
            "title": item.get("title", ""),
            "body": item.get("body", ""),
            "url": item.get("url", ""),
            "time": item.get("time") or item.get("published_at") or "",
            "score": item.get("score", 0),
        })
    return result
