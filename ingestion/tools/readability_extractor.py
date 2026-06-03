from __future__ import annotations

import logging
from typing import Optional

from ingestion.core.extraction_result import ExtractionResult

logger = logging.getLogger("ingestion.tools.readability")


def extract_with_readability(html: str, url: str) -> ExtractionResult:
    try:
        from readability import Document
    except ImportError:
        return ExtractionResult.failure(url, "readability", "readability-lxml not installed")

    try:
        doc = Document(html)
        title = doc.title() or None
        content_html = doc.summary(html_partial=True)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content_html, "lxml")
        body = soup.get_text(separator="\n", strip=True) or None

        return ExtractionResult(
            url=url,
            strategy="readability",
            success=bool(body and len(body) > 50),
            title=title,
            body=body,
            error_message=None if body else "readability produced empty body",
        )
    except Exception as exc:
        logger.warning("readability error: %s - %s", url, exc)
        return ExtractionResult.failure(url, "readability", str(exc))
