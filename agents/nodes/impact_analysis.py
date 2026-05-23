from __future__ import annotations

from agents.state.event_state import EventState
from agents.tools.llm import analyze_impact


def impact_analysis(state: EventState) -> EventState:
    normalized = state.get("normalized")
    if not normalized:
        return {**state, "impact": "[skip] no normalized event"}
    try:
        result = analyze_impact(
            title=normalized.title,
            body=normalized.body,
            theme=state.get("theme", "unknown"),
            sectors=state.get("sectors", []),
        )
        return {**state, "impact": result.impact}
    except Exception as e:
        errors = list(state.get("llm_errors") or []) + [f"impact_analysis: {type(e).__name__}: {e}"]
        return {**state, "impact": "[fallback] medium-term supply disruption risk", "llm_errors": errors}
