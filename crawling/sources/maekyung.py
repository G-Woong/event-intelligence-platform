from __future__ import annotations

import re

from crawling.sources.base import SourceCrawler


class MaekyungSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "경제 산업 뉴스 site:mk.co.kr"

    def get_entry_url(self) -> str:
        return "https://www.mk.co.kr/news"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # 매일경제 기사: /news/view/YYYY/MM/...
                if re.match(r"^https://www\.mk\.co\.kr/news/\w+/\d+/?$", href):
                    if href not in links:
                        links.append(href)
                elif re.match(r"^/news/\w+/\d+/?$", href):
                    full = "https://www.mk.co.kr" + href
                    if full not in links:
                        links.append(full)
            return links[:10]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {
            "selectors": [
                ".art_txt",
                "#newsBody",
                ".news_cnt_detail_wrap",
                "article",
                ".article_body",
            ]
        }
