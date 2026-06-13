from __future__ import annotations

from typing import Any


class QueryGenerator:
    """Generate search queries from event candidate metadata.

    Produces ko/en query variants based on entities, title, source,
    time context, and location. Synonym hook and budget controls
    are wired in Round 2.
    """

    def __init__(self, max_queries_per_candidate: int = 5) -> None:
        self.max_queries_per_candidate = max_queries_per_candidate

    def generate(self, candidate: dict[str, Any]) -> list[str]:
        """Generate search queries for a single candidate.

        Args:
            candidate: EventCandidate-shaped dict with at minimum:
                - title (str)
                - entities (list[str]) optional
                - regions (list[str]) optional

        Returns:
            List of query strings (ko + en variants, up to max_queries_per_candidate).
        """
        raise NotImplementedError("Full query generation wired in Round 2")

    def generate_batch(self, candidates: list[dict[str, Any]]) -> dict[str, list[str]]:
        """Generate queries for a batch of candidates.

        Returns:
            Dict mapping candidate['id'] (or index str) to query list.
        """
        result: dict[str, list[str]] = {}
        for i, c in enumerate(candidates):
            key = c.get("id", str(i))
            result[key] = self.generate(c)
        return result
