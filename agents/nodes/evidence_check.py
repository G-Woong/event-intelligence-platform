from __future__ import annotations

from agents.state.event_state import EventState


def evidence_check(state: EventState) -> EventState:
    return {**state, "evidence": ["[mock-source-1]", "[mock-source-2]"]}
