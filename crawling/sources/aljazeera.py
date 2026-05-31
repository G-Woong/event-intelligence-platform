from __future__ import annotations

import re

from crawling.sources.base import SourceCrawler


class AlJazeeraSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "world news site:aljazeera.com"

    def get_entry_url(self) -> str:
        return "https://www.aljazeera.com/news"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^/news/\d{4}/\d{1,2}/\d{1,2}/", href):
                    full = "https://www.aljazeera.com" + href
                    if full not in links:
                        links.append(full)
                elif re.match(r"^https://www\.aljazeera\.com/news/\d{4}/", href):
                    if href not in links:
                        links.append(href)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                ".wysiwyg",
                "article .article-p-wrapper",
                ".article__body",
                "article",
                "main",
            ]
        }
