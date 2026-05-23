from __future__ import annotations

import hashlib
from datetime import datetime
from backend.app.schemas.events import NormalizedEvent
from agents.state.event_state import EventState


def source_parse(state: EventState) -> EventState:
    raw = state["raw"]
    h = hashlib.sha256(raw.raw_text.encode()).hexdigest()[:16]
    normalized = NormalizedEvent(
        source=raw.source,
        title=raw.raw_text[:80].strip(),
        body=raw.raw_text,
        occurred_at=raw.fetched_at,
        language="en",
        hash=h,
    )
    return {**state, "normalized": normalized}
