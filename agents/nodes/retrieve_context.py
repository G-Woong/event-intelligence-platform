from __future__ import annotations

from agents.state.event_state import EventState
from agents.tools import vector_search


def retrieve_past_context(state: EventState) -> EventState:
    normalized = state.get("normalized")
    if not normalized:
        return {**state, "past_context": [], "retrieved_context": []}

    text = f"{normalized.title}\n{normalized.body[:500]}"
    try:
        hits = vector_search.search_similar(
            text, top_k=5, exclude_event_id=normalized.id
        )
        past = [f"{h['title']}: {h['summary'][:200]}" for h in hits]
        return {**state, "past_context": past, "retrieved_context": hits}
    except Exception as exc:
        errors = list(state.get("llm_errors") or [])
        errors.append(f"retrieve_past_context: {exc}")
        return {
            **state,
            "past_context": ["[fallback-context]"],
            "retrieved_context": [],
            "llm_errors": errors,
        }
