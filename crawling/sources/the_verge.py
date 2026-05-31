from __future__ import annotations

import re

from crawling.sources.base import SourceCrawler


class TheVergeSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "tech news site:theverge.com"

    def get_entry_url(self) -> str:
        return "https://www.theverge.com"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^https://www\.theverge\.com/\d{4}/\d{1,2}/\d{1,2}/", href):
                    if href not in links:
                        links.append(href)
                elif re.match(r"^/\d{4}/\d{1,2}/\d{1,2}/", href):
                    full = "https://www.theverge.com" + href
                    if full not in links:
                        links.append(full)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                ".duet--article--article-body-component",
                'div[class*="article-body"]',
                "article",
                ".c-entry-content",
                "main",
            ]
        }
