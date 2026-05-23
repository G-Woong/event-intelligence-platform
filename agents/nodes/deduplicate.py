from __future__ import annotations

from agents.state.event_state import EventState


def deduplicate_event(state: EventState) -> EventState:
    normalized = state.get("normalized")
    dedupe_key = normalized.hash if normalized else "unknown"
    # TODO(STEP-010): vector-based dedup — compare dedupe_key embedding against
    # retrieved_context scores; skip card if cosine > threshold (policy TBD).
    return {**state, "dedupe_key": dedupe_key}
