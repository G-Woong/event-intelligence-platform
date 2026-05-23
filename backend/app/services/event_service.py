from __future__ import annotations

from typing import Optional
from backend.app.schemas.events import FinalEventCard

_store: dict[str, FinalEventCard] = {}


def list_events() -> list[FinalEventCard]:
    return list(_store.values())


def get_event(event_id: str) -> Optional[FinalEventCard]:
    return _store.get(event_id)


def upsert_card(card: FinalEventCard) -> FinalEventCard:
    _store[card.id] = card
    return card
