from __future__ import annotations

from typing import Optional

from ingestion.sources.base import SourceCrawler


class BlindSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:teamblind.com"

    def get_entry_url(self) -> str:
        return "https://www.teamblind.com"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        return {
            "status": "BLOCKED",
            "reason": "Blind requires user login; no public read access to posts without authentication",
        }
