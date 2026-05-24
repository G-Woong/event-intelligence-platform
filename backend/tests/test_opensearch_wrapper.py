from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _reset_module():
    import backend.app.db.opensearch as mod
    mod._client = None
    mod._connected = False


def test_connect_success():
    _reset_module()
    mock_client = MagicMock()
    mock_client.ping.return_value = True

    with patch("backend.app.db.opensearch.get_client", return_value=mock_client):
        from backend.app.db.opensearch import connect, is_connected
        result = connect()

    assert result is True
    assert is_connected() is True


def test_connect_failure_returns_false_no_raise():
    _reset_module()
    mock_client = MagicMock()
    mock_client.ping.side_effect = Exception("connection refused")

    with patch("backend.app.db.opensearch.get_client", return_value=mock_client):
        from backend.app.db.opensearch import connect, is_connected
        result = connect()

    assert result is False
    assert is_connected() is False


def test_get_client_reuses_singleton():
    """get_client() 두 번 호출 → 동일 인스턴스 반환, OpenSearch() 1회만 호출."""
    _reset_module()
    mock_instance = MagicMock()

    with patch("opensearchpy.OpenSearch", return_value=mock_instance) as mock_cls:
        import backend.app.db.opensearch as mod
        mod._client = None
        c1 = mod.get_client()
        c2 = mod.get_client()

    assert c1 is c2
    assert c1 is mock_instance
    assert mock_cls.call_count == 1
