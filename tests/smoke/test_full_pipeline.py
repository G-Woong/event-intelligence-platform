"""Scenario A: full pipeline smoke test.

Gate: RUN_FULL_PIPELINE_SMOKE=1 (default off to avoid LLM calls in CI).
LLM_PROVIDER must be set to 'mock' (checked by fixture).
Requires full docker-compose stack (backend, worker, agent-worker) running.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import httpx

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND = os.getenv("FRONTEND_URL", "http://localhost:3000")
ADMIN_TOKEN = os.getenv("ADMIN_API_TOKEN", "")

_GATE = pytest.mark.skipif(
    os.getenv("RUN_FULL_PIPELINE_SMOKE") != "1",
    reason="set RUN_FULL_PIPELINE_SMOKE=1 to run full pipeline smoke",
)

_HEADERS: dict[str, str] = {}
if ADMIN_TOKEN:
    _HEADERS["X-Admin-Token"] = ADMIN_TOKEN


@pytest.fixture(autouse=True, scope="module")
def _check_mock_llm():
    provider = os.getenv("LLM_PROVIDER", "mock")
    if provider != "mock":
        pytest.skip("LLM_PROVIDER must be 'mock' for smoke test to avoid external API calls")


@_GATE
def test_backend_health():
    resp = httpx.get(f"{BACKEND}/health", timeout=10)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "components" in body


@_GATE
def test_frontend_health():
    resp = httpx.get(f"{FRONTEND}/api/health", timeout=10)
    assert resp.status_code == 200


@_GATE
def test_events_list_endpoint():
    resp = httpx.get(f"{BACKEND}/api/events", timeout=10)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@_GATE
def test_themes_have_name_and_count():
    resp = httpx.get(f"{BACKEND}/api/themes", timeout=10)
    assert resp.status_code == 200
    themes = resp.json()
    assert len(themes) > 0
    assert "name" in themes[0]
    assert "event_count" in themes[0]


@_GATE
def test_sectors_have_name_and_count():
    resp = httpx.get(f"{BACKEND}/api/sectors", timeout=10)
    assert resp.status_code == 200
    sectors = resp.json()
    assert len(sectors) > 0
    assert "name" in sectors[0]
    assert "event_count" in sectors[0]


@_GATE
def test_search_hit_has_id_alias():
    resp = httpx.get(f"{BACKEND}/api/events/search?q=test", timeout=10)
    # 503 is acceptable if OpenSearch has no data yet
    if resp.status_code == 503:
        pytest.skip("OpenSearch unavailable")
    assert resp.status_code == 200
    body = resp.json()
    if body["total"] > 0:
        hit = body["hits"][0]
        assert "id" in hit
        assert "card_id" in hit
        assert hit["id"] == hit["card_id"]


@_GATE
def test_reconcile_endpoint_reachable():
    resp = httpx.post(
        f"{BACKEND}/api/admin/raw-events/reconcile-stuck",
        json={"dry_run": True},
        headers=_HEADERS,
        timeout=10,
    )
    assert resp.status_code in (200, 401, 403)


@_GATE
def test_cors_preflight():
    resp = httpx.options(
        f"{BACKEND}/api/events",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
        timeout=10,
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert "localhost:3000" in acao or acao == "*", f"CORS header missing: {acao!r}"
