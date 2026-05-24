from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_search_resp(hits: list[dict], total: int = 1) -> dict:
    return {
        "hits": {
            "total": {"value": total},
            "hits": [
                {
                    "_id": h.get("card_id", "id-1"),
                    "_score": h.get("score", 0.9),
                    "_source": h,
                }
                for h in hits
            ],
        }
    }


@pytest.mark.asyncio
async def test_search_sends_multimatch_query():
    mock_client = MagicMock()
    hit = {"card_id": "id-1", "title": "Iran Sanctions", "theme": "geopolitics"}
    mock_client.search.return_value = _mock_search_resp([hit])

    with (
        patch("backend.app.services.search_service.opensearch_db") as mock_db,
        patch("backend.app.services.search_service.settings") as mock_settings,
    ):
        mock_db.get_client.return_value = mock_client
        mock_settings.OPENSEARCH_EVENT_INDEX = "event_cards"
        from backend.app.services.search_service import search_event_cards
        result = await search_event_cards("Iran")

    call_kwargs = mock_client.search.call_args[1]
    body = call_kwargs["body"]
    must = body["query"]["bool"]["must"]
    assert any("multi_match" in clause for clause in must)
    assert result["total"] == 1
    assert len(result["hits"]) == 1


@pytest.mark.asyncio
async def test_search_filter_clauses():
    mock_client = MagicMock()
    mock_client.search.return_value = _mock_search_resp([])

    with (
        patch("backend.app.services.search_service.opensearch_db") as mock_db,
        patch("backend.app.services.search_service.settings") as mock_settings,
    ):
        mock_db.get_client.return_value = mock_client
        mock_settings.OPENSEARCH_EVENT_INDEX = "event_cards"
        from backend.app.services.search_service import search_event_cards
        await search_event_cards("Iran", theme="geopolitics", sector="energy", status="published")

    body = mock_client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"theme": "geopolitics"}} in filters
    assert {"term": {"sectors": "energy"}} in filters
    assert {"term": {"status": "published"}} in filters


@pytest.mark.asyncio
async def test_search_response_shape():
    mock_client = MagicMock()
    hit_src = {
        "card_id": "abc-123",
        "title": "Test",
        "summary": "Summary here",
        "theme": "geopolitics",
        "sectors": ["energy"],
        "status": "published",
        "score": 0.88,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    mock_client.search.return_value = _mock_search_resp([hit_src], total=1)

    with (
        patch("backend.app.services.search_service.opensearch_db") as mock_db,
        patch("backend.app.services.search_service.settings") as mock_settings,
    ):
        mock_db.get_client.return_value = mock_client
        mock_settings.OPENSEARCH_EVENT_INDEX = "event_cards"
        from backend.app.services.search_service import search_event_cards
        result = await search_event_cards("Test")

    assert "total" in result
    assert "hits" in result
    h = result["hits"][0]
    assert "card_id" in h
    assert "title" in h
    assert "score" in h
