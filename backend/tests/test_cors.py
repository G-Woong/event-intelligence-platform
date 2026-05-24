from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_cors_preflight_allowed_origin():
    resp = client.options(
        "/api/events",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_preflight_admin_token_header_allowed():
    resp = client.options(
        "/api/admin/jobs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-admin-token",
        },
    )
    assert resp.status_code == 200
    allow_headers = resp.headers.get("access-control-allow-headers", "").lower()
    assert "x-admin-token" in allow_headers


def test_cors_disallowed_origin():
    resp = client.options(
        "/api/events",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") != "http://evil.example"
