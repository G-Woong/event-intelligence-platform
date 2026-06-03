from __future__ import annotations

import json
import os
from typing import Optional

from ingestion.core.source_registry import SourceSpec
from ingestion.sources.base import SourceCrawler

_HONEST_UA = "event-intelligence/0.7 (+ei)"


def _sec_ua() -> str:
    return os.environ.get("SEC_USER_AGENT") or _HONEST_UA


class SECEdgarSource(SourceCrawler):
    def __init__(self, spec: SourceSpec) -> None:
        super().__init__(spec)
        self._cached: Optional[str] = None

    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:sec.gov 8-K filing"

    def get_entry_url(self) -> str:
        return (
            "https://efts.sec.gov/LATEST/search-index"
            "?q=%228-K%22&forms=8-K"
            "&dateRange=custom&startdt=2025-01-01&enddt=2026-06-01"
        )

    def fetch_entry_html(self, url: str) -> Optional[str]:
        import httpx
        try:
            r = httpx.get(url, headers={"User-Agent": _sec_ua()}, timeout=20, follow_redirects=True)
            if r.status_code == 200:
                self._cached = r.text
                return self._cached
        except Exception:
            pass
        return None

    def fetch_page_html(self, url: str, strategy: str) -> Optional[str]:
        return self._cached

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def extract(self, html: str, url: str, strategy: str) -> Optional[dict]:
        try:
            data = json.loads(html)
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                return None
            src = hits[0].get("_source", {})
            entity = src.get("entity_name", "") or src.get("display_names", [""])[0]
            form_type = src.get("form_type", "")
            filed_at = src.get("file_date", "") or src.get("period_of_report", "")
            title = f"{entity} — {form_type}" if entity else form_type
            body_parts = [title]
            if filed_at:
                body_parts.append(f"filed={filed_at}")
            description = src.get("description", "")
            if description:
                body_parts.append(description)
            return {
                "title": title,
                "body": "\n".join(body_parts),
                "published_at": filed_at or None,
                "raw_payload": html,
                "payload_format": "json",
            }
        except Exception:
            return None
