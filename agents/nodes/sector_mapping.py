from __future__ import annotations

from agents.state.event_state import EventState
from agents.nodes.baselines import map_sectors


def theme_sector_mapping(state: EventState) -> EventState:
    """제목/본문 keyword로 theme/sector를 결정론적으로 매핑한다(고정 상수 대체).

    이전에는 모든 입력을 `theme="geopolitics", sectors=["energy","defense"]`로 고정 분류했다.
    이제는 입력에서 파생하며, 매칭이 없으면 theme="general", sectors=[]를 반환한다.
    """
    normalized = state.get("normalized")
    raw = state.get("raw")
    title = getattr(normalized, "title", None) or getattr(raw, "title", "") or ""
    body = getattr(normalized, "body", None) or getattr(raw, "raw_text", "") or ""
    source_id = getattr(raw, "source_name", "") or ""
    theme, sectors = map_sectors(title, body, source_id)
    return {**state, "theme": theme, "sectors": sectors}
