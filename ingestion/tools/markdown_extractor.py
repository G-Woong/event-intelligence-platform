from __future__ import annotations

from ingestion.core.extraction_result import ExtractionResult


def extract_markdown(html: str, url: str) -> ExtractionResult:
    """Extract markdown-formatted content from HTML using trafilatura.

    Uses trafilatura's native markdown output mode with link inclusion.
    No new dependencies — trafilatura 1.12.2 is already installed.
    """
    try:
        import trafilatura

        result = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            favor_precision=True,
            include_comments=False,
            include_tables=True,
        )
        if not result:
            return ExtractionResult.failure(url, "trafilatura_markdown", "trafilatura returned empty")

        meta = trafilatura.extract_metadata(html, default_url=url)
        return ExtractionResult(
            url=url,
            strategy="trafilatura_markdown",
            success=True,
            title=meta.title if meta else None,
            body=result,
            author=meta.author if meta else None,
            published_at=str(meta.date) if meta and meta.date else None,
            language=meta.language if meta else None,
        )
    except Exception as exc:
        return ExtractionResult.failure(url, "trafilatura_markdown", str(exc))
