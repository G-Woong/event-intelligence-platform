from __future__ import annotations

from agents.state.event_state import EventState


def publish_or_hold(state: EventState) -> EventState:
    card = state.get("final_card")
    if card and state.get("fact_check") == "pass":
        card.status = "published"
        status = "published"
    else:
        if card:
            card.status = "hold"
        status = "hold"
    return {**state, "status": status}
