from __future__ import annotations

import os
from typing import Optional

from ingestion.sources.base import SourceCrawler


class OpenDARTSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "opendart 공시"

    def get_entry_url(self) -> str:
        return "https://opendart.fss.or.kr/api/list.json"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        if not os.getenv("OPENDART_API_KEY"):
            return {
                "status": "NEEDS_API_KEY",
                "reason": "OPENDART_API_KEY not set in .env (금융감독원 DART 오픈API 인증키 필요: https://opendart.fss.or.kr)",
            }
        return None
