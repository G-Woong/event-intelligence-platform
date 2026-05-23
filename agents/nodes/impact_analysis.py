from __future__ import annotations

from agents.state.event_state import EventState


def impact_analysis(state: EventState) -> EventState:
    return {**state, "impact": "[mock] medium-term supply disruption risk"}
