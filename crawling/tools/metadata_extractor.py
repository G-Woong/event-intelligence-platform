from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("crawling.tools.metadata")


def extract_metadata(html: str, url: str) -> dict:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
    except ImportError:
        return {}

    meta: dict = {"url": url}

    title_tag = soup.find("title")
    if title_tag:
        meta["title"] = title_tag.get_text(strip=True)

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        meta["og_title"] = og_title["content"]

    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        meta["description"] = og_desc["content"]

    for name in ("description", "twitter:description"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content") and "description" not in meta:
            meta["description"] = tag["content"]

    author_tag = soup.find("meta", attrs={"name": "author"})
    if author_tag and author_tag.get("content"):
        meta["author"] = author_tag["content"]

    for prop in ("article:published_time", "og:article:published_time", "datePublished"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            meta["published_at"] = tag["content"]
            break

    lang_tag = soup.find("html")
    if lang_tag and lang_tag.get("lang"):
        meta["language"] = lang_tag["lang"]

    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        meta["canonical_url"] = canonical["href"]

    return meta


def detect_language_hint(text: str) -> Optional[str]:
    if not text:
        return None
    korean_chars = len(re.findall(r"[가-힯]", text))
    if korean_chars > 10:
        return "ko"
    chinese_chars = len(re.findall(r"[一-鿿]", text))
    if chinese_chars > 10:
        return "zh"
    return "en"
