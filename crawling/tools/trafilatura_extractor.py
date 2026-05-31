from __future__ import annotations

import logging
from typing import Optional

from crawling.core.extraction_result import ExtractionResult

logger = logging.getLogger("crawling.tools.trafilatura")


def extract_with_trafilatura(html: str, url: str) -> ExtractionResult:
    try:
        import trafilatura
    except ImportError:
        return ExtractionResult.failure(url, "trafilatura", "trafilatura not installed")

    try:
        result = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if result is None:
            return ExtractionResult.failure(url, "trafilatura", "trafilatura returned None")

        metadata = trafilatura.extract_metadata(html, default_url=url)
        title = getattr(metadata, "title", None) if metadata else None
        author = getattr(metadata, "author", None) if metadata else None
        date = getattr(metadata, "date", None) if metadata else None
        language = getattr(metadata, "language", None) if metadata else None

        body = result if isinstance(result, str) else str(result)
        return ExtractionResult(
            url=url,
            strategy="trafilatura",
            success=bool(body and len(body) > 50),
            title=title,
            body=body or None,
            author=author,
            published_at=date,
            language=language,
            error_message=None if body else "trafilatura empty body",
        )
    except Exception as exc:
        logger.warning("trafilatura error: %s - %s", url, exc)
        return ExtractionResult.failure(url, "trafilatura", str(exc))
