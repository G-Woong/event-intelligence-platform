from __future__ import annotations

from agents.state.event_state import EventState


def theme_sector_mapping(state: EventState) -> EventState:
    return {**state, "theme": "geopolitics", "sectors": ["energy", "defense"]}
