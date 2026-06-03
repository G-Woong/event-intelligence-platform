from __future__ import annotations

import os
from typing import Optional

from ingestion.sources.base import SourceCrawler


class EIASource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "EIA energy data"

    def get_entry_url(self) -> str:
        return "https://api.eia.gov/v2/natural-gas/pri/sum/data/"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        if not os.getenv("EIA_API_KEY"):
            return {
                "status": "NEEDS_API_KEY",
                "reason": "EIA_API_KEY not set in .env (EIA Open Data API key required: https://www.eia.gov/opendata/register.php)",
            }
        return None
