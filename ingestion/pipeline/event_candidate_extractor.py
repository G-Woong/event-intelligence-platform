from __future__ import annotations

from typing import Any


class EventCandidateExtractor:
    """Convert raw documents to event candidates.

    Dispatches to LLM judge (ingestion.agents.llm_judge) or mock judge
    based on LLM_PROVIDER env var. Returns structured candidate dicts
    matching EventCandidate schema.
    """

    def __init__(self, llm_provider: str = "mock") -> None:
        self.llm_provider = llm_provider

    def extract(self, raw_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract event candidates from raw documents.

        Args:
            raw_documents: list of RawDocument-shaped dicts.

        Returns:
            List of EventCandidate-shaped dicts with significance, confidence,
            entities, regions, sectors fields.
        """
        raise NotImplementedError("LLM judge wired in Round 2")
