from __future__ import annotations

import re
from typing import Optional

from ingestion.sources.base import SourceCrawler


class DCInsideSource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "site:dcinside.com"

    def get_entry_url(self) -> str:
        return "https://www.dcinside.com"

    def extract_candidate_urls(self, html: str) -> list[str]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            seen: set[str] = set()
            links: list[str] = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/board/view/\?id=", href) or re.search(r"gall\.dcinside\.com", href):
                    full = href if href.startswith("http") else "https://www.dcinside.com" + href
                    if full not in seen:
                        seen.add(full)
                        links.append(full)
            return links[:5]
        except Exception:
            return []

    def extract_source_specific_hints(self, html: str) -> dict:
        return {"selectors": [".gallery_re_txt", ".writing_view_box", "#article_list"]}

    def fallback_status(self) -> Optional[str]:
        return "BLOCKED"
