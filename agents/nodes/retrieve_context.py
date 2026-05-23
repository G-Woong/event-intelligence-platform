from __future__ import annotations

from agents.state.event_state import EventState


def retrieve_past_context(state: EventState) -> EventState:
    return {**state, "past_context": ["[mock-context-1]"]}
