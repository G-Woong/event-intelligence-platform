from __future__ import annotations

from agents.state.event_state import EventState


def entity_linking(state: EventState) -> EventState:
    text = (state.get("normalized") or state["raw"]).body if hasattr(state.get("normalized"), "body") else state["raw"].raw_text
    entities = ["[mock-entity-1]", "[mock-entity-2]"]
    return {**state, "entities": entities}
