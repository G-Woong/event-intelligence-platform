from __future__ import annotations

import re

from ingestion.sources.base import SourceCrawler


class ETNewsSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "전자 IT 산업 뉴스 site:etnews.com"

    def get_entry_url(self) -> str:
        return "https://www.etnews.com"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^/\d{9,}", href):
                    full = "https://www.etnews.com" + href
                    if full not in links:
                        links.append(full)
                elif re.match(r"^https://www\.etnews\.com/\d{9,}", href):
                    if href not in links:
                        links.append(href)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                "#articleBody",
                ".article_txt",
                ".news_view_cont",
                "article",
                ".article-body",
            ]
        }
