from __future__ import annotations

import os
from typing import Optional

from ingestion.sources.base import SourceCrawler


class YouTubeSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:youtube.com"

    def get_entry_url(self) -> str:
        return "https://www.googleapis.com/youtube/v3/search"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        if not os.getenv("YOUTUBE_API_KEY"):
            return {
                "status": "NEEDS_API_KEY",
                "reason": "YOUTUBE_API_KEY not set in .env (YouTube Data API v3 key required)",
            }
        return None
