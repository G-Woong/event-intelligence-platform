from __future__ import annotations

from typing import Optional

from ingestion.core.source_registry import SourceSpec
from ingestion.sources.base import SourceCrawler

_FIXTURE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>Dummy Article: Global Markets Update</title>
  <meta property="og:title" content="Dummy Article: Global Markets Update" />
  <meta property="og:description" content="A test article for pipeline verification." />
  <meta name="author" content="Test Author" />
  <meta property="article:published_time" content="2024-01-15T10:00:00Z" />
</head>
<body>
  <article>
    <h1>Dummy Article: Global Markets Update</h1>
    <p>This is a test fixture article for the ingestion pipeline. It contains enough
       body text to pass quality thresholds during skeleton verification.</p>
    <p>The pipeline reads this HTML, extracts the title, body, author and published_at,
       computes a quality score, runs the LLM judge (mock), and generates a report.</p>
    <p>Multiple paragraphs ensure sentence_count and body_length metrics are satisfied.
       The metadata fields are present to test metadata_completeness scoring.</p>
    <p>This content is intentionally neutral and contains no investment advice,
       buy/sell recommendations, or financial guidance of any kind.</p>
    <p>Paragraph five adds more body text to push the body_length metric above the
       minimum threshold for news-type sources (300 characters minimum).</p>
  </article>
  <a href="http://localhost/article/2">Article 2</a>
  <a href="http://localhost/article/3">Article 3</a>
</body>
</html>
"""

_FIXTURE_URLS = [
    "http://localhost/article/1",
    "http://localhost/article/2",
]


class DummySource(SourceCrawler):
    def build_search_query(self, keywords: list[str] | None = None) -> str:
        return "dummy test query"

    def get_entry_url(self) -> str:
        return "http://localhost"

    def extract_candidate_urls(self, html: str) -> list[str]:
        return _FIXTURE_URLS

    def fetch_entry_html(self, url: str) -> Optional[str]:
        return _FIXTURE_HTML

    def fetch_page_html(self, url: str, strategy: str) -> Optional[str]:
        return _FIXTURE_HTML

    def extract(self, html: str, url: str, strategy: str) -> Optional[dict]:
        return {
            "title": "Dummy Article: Global Markets Update",
            "body": (
                "This is a test fixture article for the ingestion pipeline. "
                "It contains enough body text to pass quality thresholds during skeleton verification. "
                "The pipeline reads this HTML, extracts the title, body, author and published_at, "
                "computes a quality score, runs the LLM judge (mock), and generates a report. "
                "Multiple paragraphs ensure sentence_count and body_length metrics are satisfied. "
                "This content is intentionally neutral and contains no investment advice, "
                "buy/sell recommendations, or financial guidance of any kind."
            ),
            "author": "Test Author",
            "published_at": "2024-01-15T10:00:00Z",
            "language": "en",
            "metadata": {
                "description": "A test article for pipeline verification.",
                "author": "Test Author",
                "published_at": "2024-01-15T10:00:00Z",
                "language": "en",
            },
        }
