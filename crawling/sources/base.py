from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from crawling.core.source_registry import SourceSpec


class SourceCrawler(ABC):
    def __init__(self, spec: SourceSpec) -> None:
        self.spec = spec

    @abstractmethod
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        """진입 검색 쿼리 생성."""

    @abstractmethod
    def get_entry_url(self) -> str:
        """크롤 시작 URL."""

    @abstractmethod
    def extract_candidate_urls(self, html: str) -> list[str]:
        """진입 페이지 HTML에서 후보 URL 목록 추출."""

    def get_expected_fields(self) -> list[str]:
        return self.spec.expected_fields

    def fetch_entry_html(self, url: str) -> Optional[str]:
        """Override for fixture/test sources. None = use standard fetch."""
        return None

    def fetch_page_html(self, url: str, strategy: str) -> Optional[str]:
        """Override for fixture/test sources. None = use standard fetch."""
        return None

    def extract(self, html: str, url: str, strategy: str) -> Optional[dict]:
        """Override to provide source-specific extraction. None = use standard extractor."""
        return None

    def extract_source_specific_hints(self, html: str) -> dict:
        """소스 특화 힌트 (CSS selector, 날짜 포맷 등)."""
        return {}
