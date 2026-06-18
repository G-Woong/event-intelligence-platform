from __future__ import annotations

from backend.app.core.config import settings
from backend.app.schemas.events import FinalEventCard
from agents.state.event_state import EventState
from agents.nodes.baselines import summary_baseline, contains_mock_sentinel
from agents.tools.llm import write_final_card


def final_card_writer(state: EventState) -> EventState:
    """결정론적 추출 요약을 1차로 쓰고, LLM_PROVIDER="openai"일 때만 LLM 요약으로 보강한다.

    mock provider(dev)에서는 `[mock summary] ...` 대신 원문에서 추출한 정직한 baseline 요약을 쓴다.
    status는 fail-closed로 "hold" 기본값(publish_or_hold 게이트가 승격).
    """
    normalized = state.get("normalized")
    title = getattr(normalized, "title", "") or "" if normalized else ""
    body = getattr(normalized, "body", "") or "" if normalized else ""
    entities = state.get("entities", [])

    summary = summary_baseline(title, body, entities)
    if settings.LLM_PROVIDER == "openai":
        try:
            snapshot = {
                "title": title,
                "body": body,
                "entities": entities,
                "theme": state.get("theme", "general"),
                "past_context": state.get("past_context", []),
            }
            llm_summary = write_final_card(state_snapshot=snapshot).summary
            # LLM 파싱 실패 시 write_final_card가 `[fallback summary] ...`를 반환할 수 있다 →
            # 합성 상수를 카드 요약에 넣지 않고 추출 baseline 유지.
            if not contains_mock_sentinel(llm_summary):
                summary = llm_summary
        except Exception as e:
            errors = list(state.get("llm_errors") or []) + [
                f"final_card_writer: {type(e).__name__}: {e}"
            ]
            state = {**state, "llm_errors": errors}

    card = FinalEventCard(
        title=title or "[no title]",
        summary=summary,
        theme=state.get("theme", "general"),
        sectors=state.get("sectors", []),
        entities=entities,
        impact_path=state.get("impact", ""),
        evidence=state.get("evidence", []),
        confidence_score=0.75,
        # fail-closed: publish_or_hold 게이트 통과 전까지 hold가 기본값.
        status="hold",
    )
    return {**state, "final_card": card}
