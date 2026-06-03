from __future__ import annotations

from typing import Optional

from ingestion.sources.base import SourceCrawler


class KRXKindSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:kind.krx.co.kr 공시"

    def get_entry_url(self) -> str:
        return "https://kind.krx.co.kr/disclosure/todaydisclosure.do"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        return {
            "status": "NEEDS_PLAYWRIGHT_SEARCH",
            "reason": "KRX KIND 공시 페이지는 JavaScript 동적 렌더링 필요; Playwright 기반 검색창 고도화 후 수집 가능",
        }
