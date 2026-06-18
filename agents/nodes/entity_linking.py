from __future__ import annotations

from agents.state.event_state import EventState
from agents.nodes.baselines import extract_entities


def entity_linking(state: EventState) -> EventState:
    """제목/본문에서 결정론적으로 개체를 추출한다(mock 상수 대체).

    이전에는 `["[mock-entity-1]", "[mock-entity-2]"]` 고정값을 반환했다. 이제는 입력 텍스트에서
    파생된 실제 개체만 채운다(없으면 빈 리스트). published 카드에 mock 개체가 노출되지 않는다.
    """
    normalized = state.get("normalized")
    raw = state.get("raw")
    title = getattr(normalized, "title", None) or getattr(raw, "title", "") or ""
    body = getattr(normalized, "body", None) or getattr(raw, "raw_text", "") or ""
    return {**state, "entities": extract_entities(title, body)}
