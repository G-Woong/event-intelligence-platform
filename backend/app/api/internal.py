from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.postgres import get_session
from backend.app.db.milvus import ensure_event_embeddings_collection, search_similar_events
from backend.app.services.embedding_client import get_embedding_client
from backend.app.services.event_service import get_event
from backend.app.schemas.vector import SimilarEventQuery, SimilarEventHit, SimilarEventResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/search-similar", response_model=SimilarEventResponse)
async def search_similar(
    query: SimilarEventQuery,
    session: AsyncSession = Depends(get_session),
) -> SimilarEventResponse:
    from backend.app.core.config import settings

    embedding = get_embedding_client().embed_text(query.query_text)

    try:
        ensure_event_embeddings_collection(dim=settings.EMBEDDING_DIM)
        raw_hits = search_similar_events(
            embedding=embedding,
            top_k=query.top_k,
            exclude_event_id=query.exclude_event_id,
        )
    except Exception as exc:
        logger.warning("Milvus search failed: %s", exc)
        return SimilarEventResponse(hits=[])

    hits: list[SimilarEventHit] = []
    for h in raw_hits:
        card = await get_event(session, h["event_id"])
        hits.append(SimilarEventHit(
            event_id=h["event_id"],
            card_id=h["card_id"],
            score=h["score"],
            title=card.title if card else "",
            summary=card.summary if card else "",
            theme=h.get("theme", ""),
        ))
    return SimilarEventResponse(hits=hits)
