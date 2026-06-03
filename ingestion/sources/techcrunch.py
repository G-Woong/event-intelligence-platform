from __future__ import annotations

import re

from ingestion.sources.base import SourceCrawler


class TechCrunchSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "tech news site:techcrunch.com"

    def get_entry_url(self) -> str:
        return "https://techcrunch.com"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # TechCrunch 기사: /YYYY/MM/DD/slug/ 패턴
                if re.match(r"^https://techcrunch\.com/\d{4}/\d{2}/\d{2}/", href):
                    if href not in links:
                        links.append(href)
                elif re.match(r"^/\d{4}/\d{2}/\d{2}/", href):
                    full = "https://techcrunch.com" + href
                    if full not in links:
                        links.append(full)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                ".article-content",
                ".entry-content",
                'div[class*="article__content"]',
                "article",
                ".post-content",
            ]
        }
