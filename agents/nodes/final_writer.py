from __future__ import annotations

from backend.app.schemas.events import FinalEventCard
from agents.state.event_state import EventState


def final_card_writer(state: EventState) -> EventState:
    normalized = state.get("normalized")
    card = FinalEventCard(
        title=normalized.title if normalized else "[no title]",
        summary=f"[mock summary] {(normalized.body if normalized else '')[:120]}",
        theme=state.get("theme", "general"),
        sectors=state.get("sectors", []),
        entities=state.get("entities", []),
        impact_path=state.get("impact", ""),
        evidence=state.get("evidence", []),
        confidence_score=0.75,
        status="published",
    )
    return {**state, "final_card": card}
