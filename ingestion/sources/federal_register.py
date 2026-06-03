from __future__ import annotations

import json
from typing import Optional

from ingestion.core.source_registry import SourceSpec
from ingestion.sources.base import SourceCrawler


class FederalRegisterSource(SourceCrawler):
    def __init__(self, spec: SourceSpec) -> None:
        super().__init__(spec)
        self._cached: Optional[str] = None

    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "federal register rule notice"

    def get_entry_url(self) -> str:
        return (
            "https://www.federalregister.gov/api/v1/articles.json"
            "?per_page=5&order=newest"
            "&fields[]=title&fields[]=abstract&fields[]=publication_date&fields[]=document_number"
        )

    def fetch_entry_html(self, url: str) -> Optional[str]:
        import httpx
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True)
            if r.status_code == 200:
                self._cached = r.text
                return self._cached
        except Exception:
            pass
        return None

    def fetch_page_html(self, url: str, strategy: str) -> Optional[str]:
        return self._cached

    def extract_candidate_urls(self, html: str) -> list[str]:
        return []

    def extract(self, html: str, url: str, strategy: str) -> Optional[dict]:
        try:
            data = json.loads(html)
            results = data.get("results", [])
            if not results:
                return None
            art = results[0]
            title = art.get("title", "")
            abstract = art.get("abstract") or ""
            pub_date = art.get("publication_date", "")
            doc_num = art.get("document_number", "")
            body = abstract if abstract else title
            if doc_num:
                body = f"[{doc_num}] {body}"
            return {
                "title": title,
                "body": body,
                "published_at": pub_date or None,
                "raw_payload": html,
                "payload_format": "json",
            }
        except Exception:
            return None
