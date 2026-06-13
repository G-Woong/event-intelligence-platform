from __future__ import annotations

from typing import Any


class CanonicalEventBuilder:
    """Cluster candidates and build a canonical event skeleton.

    Merges evidence from multiple sources into a single canonical event
    with claim list, evidence list, entity graph, and timeline.
    KG export hook and clustering algorithm wired in Round 2.
    """

    def build(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a canonical event from one or more candidates.

        Args:
            candidates: list of EventCandidate-shaped dicts from the same cluster.

        Returns:
            Canonical event dict with fields:
                - id, title, summary
                - claims: list[dict]
                - evidence: list[dict]
                - entities: list[str]
                - timeline: list[dict]
                - regions: list[str]
                - sectors: list[str]
                - source_ids: list[str]
        """
        raise NotImplementedError("Clustering and KG export wired in Round 2")

    def on_kg_export(self, canonical_event: dict[str, Any]) -> None:
        """Hook: called after canonical event is ready for KG/vector export."""
