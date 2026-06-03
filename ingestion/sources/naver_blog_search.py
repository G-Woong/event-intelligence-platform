from __future__ import annotations

import os
from typing import Optional

from ingestion.sources.base import SourceCrawler


class NaverBlogSearchSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "naver blog 최신"

    def get_entry_url(self) -> str:
        return "https://openapi.naver.com/v1/search/blog"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def precheck_status(self) -> Optional[dict]:
        client_id = os.getenv("NAVER_CLIENT_ID")
        client_secret = os.getenv("NAVER_CLIENT_SECRET")
        if not client_id or not client_secret:
            return {
                "status": "NEEDS_API",
                "reason": "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET not set in .env (Naver Search API 등록 필요)",
            }
        return None
