from __future__ import annotations

import re

from crawling.sources.base import SourceCrawler


class APNewsSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "breaking news site:apnews.com"

    def get_entry_url(self) -> str:
        return "https://apnews.com"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^/article/", href):
                    full = "https://apnews.com" + href
                    if full not in links:
                        links.append(full)
                elif re.match(r"^https://apnews\.com/article/", href):
                    if href not in links:
                        links.append(href)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                ".RichTextStoryBody",
                ".Article",
                'div[data-key="article"]',
                "article",
                ".story-body",
            ]
        }
