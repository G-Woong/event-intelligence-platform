from __future__ import annotations

from typing import Any


class DiscoveryCollector:
    """Run fast/discovery/community/official source crawlers.

    Stores raw_* artifacts via hook and forwards raw documents to EventQueue.
    Wires to ingestion.sources._registry.get_source_instance in Round 2.
    """

    def __init__(self, source_ids: list[str] | None = None) -> None:
        self.source_ids: list[str] = source_ids or []

    def collect(self, source_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Run each source and return raw document dicts.

        Args:
            source_ids: override self.source_ids for this run.

        Returns:
            List of raw document dicts (schema: RawDocument.model_dump()).
        """
        raise NotImplementedError("Wired in Round 2 — connect to source registry")

    def on_raw_stored(self, source_id: str, artifact_path: str) -> None:
        """Hook: called after each raw artifact is persisted."""

    def on_enqueue(self, source_id: str, candidates: list[dict[str, Any]]) -> None:
        """Hook: forward candidates to EventQueue."""
