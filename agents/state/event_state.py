from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict

from backend.app.schemas.events import RawEvent, NormalizedEvent, FinalEventCard


class EventState(TypedDict, total=False):
    raw: RawEvent
    normalized: Optional[NormalizedEvent]
    dedupe_key: Optional[str]
    entities: list[str]
    theme: str
    sectors: list[str]
    past_context: list[str]
    impact: str
    evidence: list[str]
    fact_check: str
    final_card: Optional[FinalEventCard]
    status: str
