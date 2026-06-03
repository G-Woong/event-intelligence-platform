from __future__ import annotations

import os
from typing import Optional

from ingestion.sources.base import SourceCrawler


class BOKECOSSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "한국은행 ECOS 통계"

    def get_entry_url(self) -> str:
        return "https://ecos.bok.or.kr/api/StatisticSearch"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        if not os.getenv("BOK_ECOS_API_KEY"):
            return {
                "status": "NEEDS_API_KEY",
                "reason": "BOK_ECOS_API_KEY not set in .env (한국은행 ECOS 오픈API 인증키 필요: https://ecos.bok.or.kr)",
            }
        return None
