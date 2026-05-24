from __future__ import annotations

import logging

from backend.app.core.config import settings
from backend.app.db import opensearch as opensearch_db

logger = logging.getLogger(__name__)


class OpenSearchUnavailable(Exception):
    pass


def _hit_to_dict(hit: dict) -> dict:
    src = hit.get("_source", {})
    return {
        "card_id": src.get("card_id", hit.get("_id", "")),
        "title": src.get("title", ""),
        "summary": src.get("summary"),
        "theme": src.get("theme"),
        "sectors": src.get("sectors", []),
        "status": src.get("status"),
        "score": hit.get("_score", 0.0),
        "created_at": src.get("created_at"),
    }


async def search_event_cards(
    q: str,
    theme: str | None = None,
    sector: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    try:
        client = opensearch_db.get_client()
    except Exception as exc:
        logger.warning("opensearch client unavailable: %s", exc)
        raise OpenSearchUnavailable(str(exc)) from exc

    must = [{"multi_match": {"query": q, "fields": ["title^2", "summary", "text_all"]}}]
    filter_clauses: list[dict] = []
    if theme:
        filter_clauses.append({"term": {"theme": theme}})
    if sector:
        filter_clauses.append({"term": {"sectors": sector}})
    if status:
        filter_clauses.append({"term": {"status": status}})

    body: dict = {
        "query": {"bool": {"must": must, "filter": filter_clauses}},
        "from": offset,
        "size": limit,
    }

    try:
        resp = client.search(index=settings.OPENSEARCH_EVENT_INDEX, body=body)
    except Exception as exc:
        logger.warning("opensearch search failed: %s", exc)
        raise OpenSearchUnavailable(str(exc)) from exc

    return {
        "total": resp["hits"]["total"]["value"],
        "hits": [_hit_to_dict(h) for h in resp["hits"]["hits"]],
    }
