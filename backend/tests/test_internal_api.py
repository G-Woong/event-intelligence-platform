from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.security import require_admin_token
from backend.app.db.postgres import get_session


@pytest.fixture()
def client(mock_session):
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[require_admin_token] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def test_search_similar_returns_empty_on_milvus_failure(client):
    with (
        patch("backend.app.api.internal.get_embedding_client") as mock_embed,
        patch("backend.app.api.internal.ensure_event_embeddings_collection"),
        patch("backend.app.api.internal.search_similar_events", side_effect=RuntimeError("milvus down")),
    ):
        mock_embed.return_value.embed_text.return_value = [0.1] * 1536
        resp = client.post("/api/internal/search-similar", json={"query_text": "test event"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["hits"] == []


def test_search_similar_response_schema(client):
    from backend.app.schemas.events import FinalEventCard
    from datetime import datetime, timezone

    fake_card = FinalEventCard(
        id="evt-001",
        title="Big Earthquake",
        summary="Major earthquake struck region X.",
        theme="disaster",
    )

    with (
        patch("backend.app.api.internal.get_embedding_client") as mock_embed,
        patch("backend.app.api.internal.ensure_event_embeddings_collection"),
        patch(
            "backend.app.api.internal.search_similar_events",
            return_value=[{"event_id": "evt-001", "card_id": "evt-001", "score": 0.95, "theme": "disaster"}],
        ),
        patch("backend.app.api.internal.get_event", new=AsyncMock(return_value=fake_card)),
    ):
        mock_embed.return_value.embed_text.return_value = [0.1] * 1536
        resp = client.post(
            "/api/internal/search-similar",
            json={"query_text": "earthquake", "top_k": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["hits"]) == 1
        hit = body["hits"][0]
        assert hit["event_id"] == "evt-001"
        assert hit["title"] == "Big Earthquake"
        assert "score" in hit


def test_search_similar_exclude_event_id(client):
    with (
        patch("backend.app.api.internal.get_embedding_client") as mock_embed,
        patch("backend.app.api.internal.ensure_event_embeddings_collection"),
        patch("backend.app.api.internal.search_similar_events", return_value=[]) as mock_search,
        patch("backend.app.api.internal.get_event", new=AsyncMock(return_value=None)),
    ):
        mock_embed.return_value.embed_text.return_value = [0.1] * 1536
        resp = client.post(
            "/api/internal/search-similar",
            json={"query_text": "test", "exclude_event_id": "evt-self"},
        )
        assert resp.status_code == 200
        _, kwargs = mock_search.call_args
        assert kwargs.get("exclude_event_id") == "evt-self"
