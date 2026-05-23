from __future__ import annotations

from agents.state.event_state import EventState


def deduplicate_event(state: EventState) -> EventState:
    normalized = state.get("normalized")
    dedupe_key = normalized.hash if normalized else "unknown"
    return {**state, "dedupe_key": dedupe_key}
