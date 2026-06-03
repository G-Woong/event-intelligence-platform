from __future__ import annotations

import re
from typing import Optional

from ingestion.sources.base import SourceCrawler


class EUPressCornerSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:ec.europa.eu/commission/presscorner"

    def get_entry_url(self) -> str:
        return "https://ec.europa.eu/commission/presscorner/home/en"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            seen: set[str] = set()
            links: list[str] = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/presscorner/detail/", href):
                    full = href if href.startswith("http") else "https://ec.europa.eu" + href
                    if full not in seen:
                        seen.add(full)
                        links.append(full)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                ".ecl-editor",
                ".press-release-content",
                ".ecl-paragraph",
                "article",
                "main",
            ]
        }
