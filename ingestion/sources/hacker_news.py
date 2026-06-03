from __future__ import annotations

import json
from typing import Optional

from ingestion.core.source_registry import SourceSpec
from ingestion.sources.base import SourceCrawler

_BASE = "https://hacker-news.firebaseio.com/v0"


class HackerNewsSource(SourceCrawler):
    def __init__(self, spec: SourceSpec) -> None:
        super().__init__(spec)
        self._item_json: Optional[str] = None

    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:news.ycombinator.com"

    def get_entry_url(self) -> str:
        return f"{_BASE}/topstories.json"

    def fetch_entry_html(self, url: str) -> Optional[str]:
        import httpx
        try:
            r = httpx.get(url, timeout=10)
            if r.status_code != 200:
                return None
            ids: list[int] = r.json()
            if not ids:
                return None
            item_url = f"{_BASE}/item/{ids[0]}.json"
            r2 = httpx.get(item_url, timeout=10)
            if r2.status_code == 200:
                self._item_json = r2.text
                return self._item_json
        except Exception:
            pass
        return None

    def fetch_page_html(self, url: str, strategy: str) -> Optional[str]:
        return self._item_json

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def extract(self, html: str, url: str, strategy: str) -> Optional[dict]:
        try:
            item = json.loads(html)
            title = item.get("title", "")
            item_url = item.get("url", "")
            score = item.get("score", 0)
            descendants = item.get("descendants", 0)
            # body는 title + url 결합으로 요약
            body = f"{title}\n{item_url}" if item_url else title
            return {
                "title": title,
                "body": body,
                "published_at": None,
                "engagement": f"score={score} comments={descendants}",
                "raw_payload": html,
                "payload_format": "json",
            }
        except Exception:
            return None
