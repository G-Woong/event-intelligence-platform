from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.security import require_admin_token
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


def _get_jobs(client: TestClient, token: str | None = None) -> int:
    headers = {"X-Admin-Token": token} if token is not None else {}
    resp = client.get("/api/admin/jobs", headers=headers)
    return resp.status_code


def test_unset_token_no_header_allows(client):
    """ADMIN_API_TOKEN 미설정 + 헤더 없음 → 200 (dev allow)."""
    with patch("backend.app.core.security.settings") as mock_settings:
        mock_settings.ADMIN_API_TOKEN = ""
        assert _get_jobs(client) == 200


def test_set_token_no_header_rejects(client):
    """ADMIN_API_TOKEN 설정 + 헤더 없음 → 401."""
    with patch("backend.app.core.security.settings") as mock_settings:
        mock_settings.ADMIN_API_TOKEN = "secrettoken"
        assert _get_jobs(client) == 401


def test_set_token_wrong_header_rejects(client):
    """ADMIN_API_TOKEN 설정 + 잘못된 헤더 → 401."""
    with patch("backend.app.core.security.settings") as mock_settings:
        mock_settings.ADMIN_API_TOKEN = "secrettoken"
        assert _get_jobs(client, token="wrongtoken") == 401


def test_set_token_correct_header_allows(client):
    """ADMIN_API_TOKEN 설정 + 올바른 헤더 → 200."""
    with patch("backend.app.core.security.settings") as mock_settings:
        mock_settings.ADMIN_API_TOKEN = "secrettoken"
        assert _get_jobs(client, token="secrettoken") == 200


def test_jobs_endpoint_is_protected(client):
    """/api/admin/jobs 보호 적용 확인."""
    with patch("backend.app.core.security.settings") as mock_settings:
        mock_settings.ADMIN_API_TOKEN = "mytoken"
        assert _get_jobs(client) == 401
        assert _get_jobs(client, token="mytoken") == 200


def test_internal_search_similar_is_protected(client):
    """/api/internal/search-similar 보호 적용 확인."""
    with patch("backend.app.core.security.settings") as mock_settings:
        mock_settings.ADMIN_API_TOKEN = "mytoken"
        resp_no_token = client.post("/api/internal/search-similar", json={"query_text": "test"})
        assert resp_no_token.status_code == 401

        with (
            patch("backend.app.api.internal.get_embedding_client") as mock_embed,
            patch("backend.app.api.internal.ensure_event_embeddings_collection"),
            patch("backend.app.api.internal.search_similar_events", return_value=[]),
        ):
            mock_embed.return_value.embed_text.return_value = [0.1] * 1536
            resp_with_token = client.post(
                "/api/internal/search-similar",
                json={"query_text": "test"},
                headers={"X-Admin-Token": "mytoken"},
            )
        assert resp_with_token.status_code == 200
