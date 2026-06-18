"""운영(production/staging)에서 ADMIN_API_TOKEN 미설정 시 admin API fail-closed 검증.

dev/test에서는 dev 편의 bypass를 유지하되, 운영성 환경에서는 토큰 미설정을 거부한다.
"""
from __future__ import annotations

from types import SimpleNamespace
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


def _patched_settings(app_env: str, token: str):
    return SimpleNamespace(APP_ENV=app_env, ADMIN_API_TOKEN=token)


def test_production_missing_token_rejects(client):
    """production + 토큰 미설정 → 503 (unconfigured, fail-closed)."""
    with patch("backend.app.core.security.settings", _patched_settings("production", "")):
        resp = client.get("/api/admin/jobs")
        assert resp.status_code == 503


def test_staging_missing_token_rejects(client):
    """staging + 토큰 미설정 → 503."""
    with patch("backend.app.core.security.settings", _patched_settings("staging", "")):
        assert client.get("/api/admin/jobs").status_code == 503


def test_dev_missing_token_allows(client):
    """dev + 토큰 미설정 → 200 (dev 편의 bypass 유지)."""
    with patch("backend.app.core.security.settings", _patched_settings("dev", "")):
        assert client.get("/api/admin/jobs").status_code == 200


def test_test_env_missing_token_allows(client):
    """test 환경 + 토큰 미설정 → 200 (CI 편의 유지)."""
    with patch("backend.app.core.security.settings", _patched_settings("test", "")):
        assert client.get("/api/admin/jobs").status_code == 200


def test_production_with_token_requires_header(client):
    """production + 토큰 설정 → 헤더 없으면 401, 올바른 헤더면 200."""
    with patch("backend.app.core.security.settings", _patched_settings("production", "prodtoken")):
        assert client.get("/api/admin/jobs").status_code == 401
        assert client.get("/api/admin/jobs", headers={"X-Admin-Token": "prodtoken"}).status_code == 200
