from __future__ import annotations

import logging
from typing import Optional

from ingestion.core.extraction_result import ExtractionResult

logger = logging.getLogger("ingestion.tools.dom_candidate")

_ARTICLE_SELECTORS = [
    "article",
    '[role="main"]',
    ".article-body",
    ".post-content",
    ".entry-content",
    ".story-body",
    "#article-content",
    ".news-body",
    "main",
]


def extract_with_dom_heuristic(html: str, url: str) -> ExtractionResult:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ExtractionResult.failure(url, "dom_heuristic", "beautifulsoup4 not installed")

    try:
        soup = BeautifulSoup(html, "lxml")

        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None

        body = None
        for selector in _ARTICLE_SELECTORS:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    body = text
                    break

        if not body:
            paragraphs = soup.find_all("p")
            body = "\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)

        from ingestion.tools.metadata_extractor import extract_metadata, detect_language_hint
        meta = extract_metadata(html, url)
        language = detect_language_hint(body or "")

        return ExtractionResult(
            url=url,
            strategy="dom_heuristic",
            success=bool(body and len(body) > 50),
            title=title,
            body=body or None,
            author=meta.get("author"),
            published_at=meta.get("published_at"),
            language=language,
            metadata=meta,
            error_message=None if body else "dom_heuristic: no content found",
        )
    except Exception as exc:
        logger.warning("dom_heuristic error: %s - %s", url, exc)
        return ExtractionResult.failure(url, "dom_heuristic", str(exc))
