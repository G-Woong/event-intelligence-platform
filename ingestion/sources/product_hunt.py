from __future__ import annotations

import os
from typing import Optional

from ingestion.sources.base import SourceCrawler


class ProductHuntSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:producthunt.com"

    def get_entry_url(self) -> str:
        return "https://api.producthunt.com/v2/api/graphql"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        if not os.getenv("PRODUCT_HUNT_API_KEY"):
            return {
                "status": "NEEDS_API_KEY",
                "reason": "PRODUCT_HUNT_API_KEY not set in .env (OAuth 2.0 / Developer Token required)",
            }
        return None
