from __future__ import annotations

import re

from crawling.sources.base import SourceCrawler


class YNASource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "최신 뉴스 site:yna.co.kr"

    def get_entry_url(self) -> str:
        return "https://www.yna.co.kr/news"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # 연합뉴스 기사 URL: /view/AKR... 또는 /news/view/AKR...
                if re.search(r"/view/AKR\d+", href):
                    if href.startswith("/"):
                        full = "https://www.yna.co.kr" + href
                    else:
                        full = href
                    if full not in links:
                        links.append(full)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                ".article",
                ".story-news article",
                ".article-txt",
                "#articleWrap",
                "article",
            ]
        }
