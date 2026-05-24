from __future__ import annotations

import logging

from backend.app.core.config import settings
from backend.app.db import opensearch as opensearch_db
from backend.app.schemas.events import FinalEventCard

logger = logging.getLogger(__name__)

_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "card_id": {"type": "keyword"},
            "title": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "summary": {"type": "text"},
            "text_all": {"type": "text"},
            "theme": {"type": "keyword"},
            "status": {"type": "keyword"},
            "sectors": {"type": "keyword"},
            "entities": {"type": "keyword"},
            "confidence_score": {"type": "float"},
            "created_at": {"type": "date"},
        }
    }
}


def _card_to_doc(card: FinalEventCard) -> dict:
    text_all = " ".join(filter(None, [
        card.title,
        card.summary,
        " ".join(card.entities or []),
        " ".join(card.sectors or []),
    ]))
    return {
        "card_id": str(card.id),
        "title": card.title,
        "summary": card.summary,
        "theme": card.theme,
        "sectors": card.sectors or [],
        "entities": card.entities or [],
        "status": card.status,
        "confidence_score": card.confidence_score,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "text_all": text_all,
    }


def ensure_event_cards_index() -> None:
    client = opensearch_db.get_client()
    index = settings.OPENSEARCH_EVENT_INDEX
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body=_INDEX_MAPPING)
        logger.info("OpenSearch index created: %s", index)


def try_index_card(card: FinalEventCard) -> None:
    try:
        client = opensearch_db.get_client()
        doc = _card_to_doc(card)
        client.index(
            index=settings.OPENSEARCH_EVENT_INDEX,
            id=str(card.id),
            body=doc,
            refresh=False,
        )
    except Exception as exc:
        logger.warning("opensearch index failed for card=%s: %s", card.id, exc)
