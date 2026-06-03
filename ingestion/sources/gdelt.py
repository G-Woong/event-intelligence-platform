from __future__ import annotations

import json
from typing import Optional

from ingestion.core.source_registry import SourceSpec
from ingestion.sources.base import SourceCrawler


class GDELTSource(SourceCrawler):
    def __init__(self, spec: SourceSpec) -> None:
        super().__init__(spec)
        self._cached: Optional[str] = None

    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "gdelt world events"

    def get_entry_url(self) -> str:
        return (
            "https://api.gdeltproject.org/api/v2/doc/doc"
            "?query=world+news&mode=artlist&maxrecords=5&format=json"
        )

    def fetch_entry_html(self, url: str) -> Optional[str]:
        import httpx
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True)
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
            articles = data.get("articles", [])
            if not articles:
                return None
            art = articles[0]
            title = art.get("title", "")
            source_url = art.get("url", "")
            seendate = art.get("seendate", "")
            tone = art.get("tone", "")
            body_parts = [title]
            if source_url:
                body_parts.append(source_url)
            if seendate:
                body_parts.append(f"seendate={seendate}")
            if tone:
                body_parts.append(f"tone={tone}")
            return {
                "title": title,
                "body": "\n".join(body_parts),
                "published_at": seendate or None,
                "raw_payload": html,
                "payload_format": "json",
            }
        except Exception:
            return None
