from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.postgres import get_session


@pytest.fixture()
def mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture()
def client(mock_session):
    app.dependency_overrides[get_session] = lambda: mock_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_SEARCH_RESULT = {
    "total": 1,
    "hits": [
        {
            "card_id": "id-1",
            "id": "id-1",
            "title": "Iran Sanctions",
            "summary": "Details.",
            "theme": "geopolitics",
            "sectors": ["energy"],
            "status": "published",
            "score": 0.9,
            "confidence_score": 0.85,
            "created_at": None,
        }
    ],
}


def test_search_returns_200_with_hits(client):
    with patch(
        "backend.app.api.events.search_event_cards",
        new_callable=AsyncMock,
        return_value=_SEARCH_RESULT,
    ):
        resp = client.get("/api/events/search?q=Iran")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["hits"][0]["card_id"] == "id-1"
    assert data["hits"][0]["id"] == "id-1"
    assert data["hits"][0]["confidence_score"] == 0.85


def test_search_missing_q_returns_422(client):
    resp = client.get("/api/events/search")
    assert resp.status_code == 422


def test_search_opensearch_unavailable_returns_503(client):
    from backend.app.services.search_service import OpenSearchUnavailable
    with patch(
        "backend.app.api.events.search_event_cards",
        new_callable=AsyncMock,
        side_effect=OpenSearchUnavailable("down"),
    ):
        resp = client.get("/api/events/search?q=Iran")
    assert resp.status_code == 503


def test_search_passes_filters_to_service(client):
    with patch(
        "backend.app.api.events.search_event_cards",
        new_callable=AsyncMock,
        return_value={"total": 0, "hits": []},
    ) as mock_svc:
        resp = client.get("/api/events/search?q=Iran&theme=geopolitics&sector=energy&limit=5&offset=10")
    assert resp.status_code == 200
    mock_svc.assert_called_once_with("Iran", "geopolitics", "energy", None, 5, 10)
