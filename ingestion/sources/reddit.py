from __future__ import annotations

import json
from typing import Optional

from ingestion.core.source_registry import SourceSpec
from ingestion.sources.base import SourceCrawler


class RedditSource(SourceCrawler):
    def __init__(self, spec: SourceSpec) -> None:
        super().__init__(spec)
        self._cached: Optional[str] = None

    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:reddit.com worldnews"

    def get_entry_url(self) -> str:
        return "https://www.reddit.com/r/worldnews.json?limit=5"

    def fetch_entry_html(self, url: str) -> Optional[str]:
        import httpx
        headers = {"User-Agent": "event-intelligence/1.0 (research; contact: research@example.com)"}
        try:
            r = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
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
            posts = data.get("data", {}).get("children", [])
            if not posts:
                return None
            post = posts[0]["data"]
            title = post.get("title", "")
            selftext = post.get("selftext") or ""
            body = selftext if len(selftext) > 30 else title
            score = post.get("score", 0)
            num_comments = post.get("num_comments", 0)
            return {
                "title": title,
                "body": body,
                "published_at": None,
                "engagement": f"score={score} comments={num_comments}",
                "raw_payload": html,
                "payload_format": "json",
            }
        except Exception:
            return None

    def fallback_status(self) -> Optional[str]:
        return "NEEDS_API"
