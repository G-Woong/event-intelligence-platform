from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.security import require_admin_token
from backend.app.db.postgres import get_session
from backend.app.schemas.events import FinalEventCard


def _make_card(**kwargs) -> FinalEventCard:
    defaults = dict(title="T", summary="S", theme="geo")
    defaults.update(kwargs)
    return FinalEventCard(**defaults)


@pytest.fixture()
def mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture()
def client(mock_session):
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[require_admin_token] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_reindex_returns_indexed_count(client):
    cards = [_make_card() for _ in range(3)]
    with (
        patch("backend.app.api.admin.event_service.list_events", new_callable=AsyncMock, return_value=cards),
        patch("backend.app.api.admin.opensearch_index_service.ensure_event_cards_index"),
        patch("backend.app.api.admin.opensearch_index_service.try_index_card"),
    ):
        resp = client.post("/api/admin/search/reindex", json={"limit": 100, "dry_run": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["indexed"] == 3
    assert data["dry_run"] is False


def test_reindex_dry_run_skips_indexing(client):
    cards = [_make_card() for _ in range(2)]
    with (
        patch("backend.app.api.admin.event_service.list_events", new_callable=AsyncMock, return_value=cards),
        patch("backend.app.api.admin.opensearch_index_service.ensure_event_cards_index") as mock_ensure,
        patch("backend.app.api.admin.opensearch_index_service.try_index_card") as mock_try,
    ):
        resp = client.post("/api/admin/search/reindex", json={"limit": 100, "dry_run": True})
    assert resp.status_code == 200
    assert resp.json()["indexed"] == 2
    assert resp.json()["dry_run"] is True
    mock_ensure.assert_not_called()
    mock_try.assert_not_called()


def test_reindex_requires_admin_token():
    with TestClient(app) as c:
        with patch("backend.app.core.security.settings") as mock_settings:
            mock_settings.ADMIN_API_TOKEN = "secrettoken"
            resp = c.post("/api/admin/search/reindex", json={})
    assert resp.status_code == 401
