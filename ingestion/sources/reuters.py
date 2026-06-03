from __future__ import annotations

import re
from typing import Optional

from ingestion.sources.base import SourceCrawler


class ReutersSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "breaking news site:reuters.com"

    def get_entry_url(self) -> str:
        return "https://www.reuters.com/news"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            seen: set[str] = set()
            links: list[str] = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/world/|/business/|/markets/|/technology/", href):
                    full = href if href.startswith("http") else "https://www.reuters.com" + href
                    if full not in seen and "reuters.com" in full:
                        seen.add(full)
                        links.append(full)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                "[data-testid='paragraph-0']",
                ".article-body__content",
                ".StandardArticleBody_body",
                "article",
            ]
        }

    def fallback_status(self) -> Optional[str]:
        return "NEEDS_LICENSE_OR_API"
