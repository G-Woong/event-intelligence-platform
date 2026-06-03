from __future__ import annotations

import re

from ingestion.sources.base import SourceCrawler


class HankyungSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "경제 금융 뉴스 site:hankyung.com"

    def get_entry_url(self) -> str:
        return "https://www.hankyung.com/all-news"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # 한국경제 기사: /article/YYYYMMDDXXX
                if re.match(r"^https://www\.hankyung\.com/article/\d+", href):
                    if href not in links:
                        links.append(href)
                elif re.match(r"^/article/\d+", href):
                    full = "https://www.hankyung.com" + href
                    if full not in links:
                        links.append(full)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                "#articlebody",
                ".article-body",
                ".content-body",
                "article",
                "#article_body",
            ]
        }
