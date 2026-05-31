from __future__ import annotations

import re

from crawling.sources.base import SourceCrawler


class ZDNetKoreaSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "IT 기술 뉴스 site:zdnet.co.kr"

    def get_entry_url(self) -> str:
        return "https://zdnet.co.kr"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^/view/\?no=\d+", href):
                    full = "https://zdnet.co.kr" + href
                    if full not in links:
                        links.append(full)
                elif re.match(r"^https://zdnet\.co\.kr/view/\?no=\d+", href):
                    if href not in links:
                        links.append(href)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                ".view_cont",
                "#articleBody",
                ".article_body",
                "article",
                ".news_view",
            ]
        }
