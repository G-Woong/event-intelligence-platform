from __future__ import annotations

from typing import Any


class SearchEnrichmentCollector:
    """Enrich event candidates with targeted search queries.

    Accepts raw event candidates, generates search queries via QueryGenerator,
    and calls registered search sources (serper, exa, newsapi, guardian, etc.).
    Wired to Phase 4 search_enrichment sources in Round 2.
    """

    def __init__(self, search_source_ids: list[str] | None = None) -> None:
        self.search_source_ids: list[str] = search_source_ids or []

    def enrich(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Generate search queries for each candidate and collect results.

        Args:
            candidates: list of event candidate dicts from EventCandidateExtractor.

        Returns:
            List of enriched candidate dicts with additional search evidence attached.
        """
        raise NotImplementedError("Wired in Round 2 — connect to search source registry")
