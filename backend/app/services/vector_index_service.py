from __future__ import annotations

import hashlib
import json
import logging

from backend.app.schemas.events import FinalEventCard
from backend.app.services.embedding_client import get_embedding_client
from backend.app.db.milvus import ensure_event_embeddings_collection, insert_event_embedding

logger = logging.getLogger(__name__)


async def try_index_card(card: FinalEventCard) -> None:
    """Embed + Milvus insert after PG upsert. Failures are swallowed so PG write is never blocked."""
    try:
        from backend.app.core.config import settings

        text = f"{card.title}\n{card.summary}"
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]

        ensure_event_embeddings_collection(dim=settings.EMBEDDING_DIM)

        embedding = get_embedding_client().embed_text(text)

        metadata = json.dumps({
            "sectors": card.sectors,
            "entities": card.entities,
        })[:2048]

        insert_event_embedding(
            event_id=card.id,
            embedding=embedding,
            card_id=card.id,
            text_hash=text_hash,
            theme=card.theme or "",
            source_type="agent",
            metadata_json=metadata,
        )
    except Exception as exc:
        logger.warning("vector index failed for card=%s: %s", card.id, exc)
