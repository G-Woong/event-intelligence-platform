from __future__ import annotations

import re
from typing import Optional

from crawling.core.source_registry import SourceSpec
from crawling.sources.base import SourceCrawler


class BBCSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "breaking news site:bbc.com/news"

    def get_entry_url(self) -> str:
        return "https://www.bbc.com/news"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            seen = set()
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^/news/articles/[a-z0-9]+", href):
                    full = "https://www.bbc.com" + href
                    if full not in seen:
                        seen.add(full)
                        links.append(full)
                elif re.match(r"^https://www\.bbc\.com/news/articles/[a-z0-9]+", href):
                    if href not in seen:
                        seen.add(href)
                        links.append(href)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                '[data-component="text-block"]',
                "article",
                ".ssrcss-11r1m41-RichTextComponentWrapper",
                "#main-content",
                ".story-body",
            ]
        }
