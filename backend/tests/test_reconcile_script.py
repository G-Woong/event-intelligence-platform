from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from scripts.reconcile_stuck_once import main


def _mock_resp(status_code: int = 200, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {"stuck_count": 0, "marked_failed": 0, "dry_run": True, "items": []}
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        resp.raise_for_status.side_effect = HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=status_code)
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_happy_path_exits_zero(capsys):
    payload = {"stuck_count": 2, "marked_failed": 0, "dry_run": True, "items": []}
    with patch("httpx.post", return_value=_mock_resp(200, payload)) as mock_post:
        code = main()

    assert code == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["stuck_count"] == 2
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "reconcile-stuck" in call_kwargs[0][0]
    assert call_kwargs[1]["json"]["dry_run"] is True


def test_http_failure_exits_one(capsys):
    with patch("httpx.post", return_value=_mock_resp(500)):
        code = main()

    assert code == 1
    captured = capsys.readouterr()
    assert "reconcile_stuck_once failed" in captured.err


def test_env_override_sets_payload(monkeypatch):
    monkeypatch.setenv("RECONCILER_BEFORE_SECONDS", "120")
    monkeypatch.setenv("RECONCILER_LIMIT", "10")
    monkeypatch.setenv("RECONCILER_DRY_RUN", "false")
    monkeypatch.setenv("ADMIN_API_TOKEN", "devtoken")

    with patch("httpx.post", return_value=_mock_resp(200)) as mock_post:
        code = main()

    assert code == 0
    call_kwargs = mock_post.call_args
    body = call_kwargs[1]["json"]
    assert body["before_seconds"] == 120
    assert body["limit"] == 10
    assert body["dry_run"] is False
    headers = call_kwargs[1]["headers"]
    assert headers.get("X-Admin-Token") == "devtoken"
