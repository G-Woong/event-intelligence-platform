from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.reindex_opensearch_once import main


def _mock_resp(status_code: int = 200, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {"indexed": 5, "dry_run": True}
    if status_code >= 400:
        from httpx import HTTPStatusError
        resp.raise_for_status.side_effect = HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=status_code)
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_happy_path_exits_zero(capsys):
    payload = {"indexed": 10, "dry_run": True}
    with patch("httpx.post", return_value=_mock_resp(200, payload)) as mock_post:
        code = main()

    assert code == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["indexed"] == 10
    mock_post.assert_called_once()
    call_url = mock_post.call_args[0][0]
    assert "reindex" in call_url


def test_http_failure_exits_one(capsys):
    with patch("httpx.post", return_value=_mock_resp(500)):
        code = main()

    assert code == 1
    captured = capsys.readouterr()
    assert "reindex_opensearch_once failed" in captured.err


def test_env_override_sets_payload(monkeypatch):
    monkeypatch.setenv("REINDEX_LIMIT", "50")
    monkeypatch.setenv("REINDEX_DRY_RUN", "false")
    monkeypatch.setenv("ADMIN_API_TOKEN", "mytoken")

    with patch("httpx.post", return_value=_mock_resp(200)) as mock_post:
        code = main()

    assert code == 0
    call_kwargs = mock_post.call_args
    body = call_kwargs[1]["json"]
    assert body["limit"] == 50
    assert body["dry_run"] is False
    headers = call_kwargs[1]["headers"]
    assert headers.get("X-Admin-Token") == "mytoken"
