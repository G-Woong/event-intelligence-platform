from __future__ import annotations

from typing import Optional

from ingestion.sources.base import SourceCrawler


class XSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:twitter.com"

    def get_entry_url(self) -> str:
        return "https://twitter.com"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        return {
            "status": "BLOCKED",
            "reason": "X(Twitter) requires login or API bearer token; public timeline not accessible without auth",
        }
