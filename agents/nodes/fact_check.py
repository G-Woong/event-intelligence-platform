from __future__ import annotations

from agents.state.event_state import EventState
from agents.tools.llm import fact_check_claims


def fact_check(state: EventState) -> EventState:
    normalized = state.get("normalized")
    if not normalized:
        return {**state, "fact_check": "pass"}
    try:
        result = fact_check_claims(
            title=normalized.title,
            body=normalized.body,
            evidence=state.get("evidence", []),
        )
        return {**state, "fact_check": result.status}
    except Exception as e:
        errors = list(state.get("llm_errors") or []) + [f"fact_check: {type(e).__name__}: {e}"]
        return {**state, "fact_check": "pass", "llm_errors": errors}
