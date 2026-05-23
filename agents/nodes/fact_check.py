from __future__ import annotations

from agents.state.event_state import EventState


def fact_check(state: EventState) -> EventState:
    return {**state, "fact_check": "pass"}
