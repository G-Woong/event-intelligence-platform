from __future__ import annotations

from backend.app.schemas.events import FinalEventCard
from agents.state.event_state import EventState
from agents.tools.llm import write_final_card


def final_card_writer(state: EventState) -> EventState:
    normalized = state.get("normalized")

    try:
        snapshot = {
            "title": normalized.title if normalized else "",
            "body": normalized.body if normalized else "",
            "entities": state.get("entities", []),
            "theme": state.get("theme", "general"),
            "past_context": state.get("past_context", []),
        }
        llm_result = write_final_card(state_snapshot=snapshot)
        summary = llm_result.summary
    except Exception as e:
        errors = list(state.get("llm_errors") or []) + [f"final_card_writer: {type(e).__name__}: {e}"]
        body_text = normalized.body if normalized else ""
        summary = f"[mock summary] {body_text[:120]}"
        state = {**state, "llm_errors": errors}

    card = FinalEventCard(
        title=normalized.title if normalized else "[no title]",
        summary=summary,
        theme=state.get("theme", "general"),
        sectors=state.get("sectors", []),
        entities=state.get("entities", []),
        impact_path=state.get("impact", ""),
        evidence=state.get("evidence", []),
        confidence_score=0.75,
        # fail-closed: publish_or_hold 게이트 통과 전까지 hold가 기본값(P0 하드닝).
        status="hold",
    )
    return {**state, "final_card": card}
