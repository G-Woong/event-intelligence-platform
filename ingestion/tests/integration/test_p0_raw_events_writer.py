"""P0: BackendApiRawEventsWriter 동작 — created/duplicate/server-error/client-error(네트워크 0).

httpx.MockTransport 로 backend 응답을 모사한다. 실 backend 불필요.
"""
from __future__ import annotations

import httpx
import pytest

from ingestion.integration import downstream_contracts as contracts
from ingestion.integration.raw_events_writer import (
    BackendApiRawEventsWriter,
    MirrorRawEventsWriter,
)

_CREATE = {
    "source_type": "article",
    "source_name": "ap_news",
    "url": "https://ap.test/a",
    "content_hash": "a" * 64,
    "raw_text": "",
    "raw_metadata": {"record_type": "article_candidate", "dedup_key": "ap_news:1"},
}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_created_returns_true_and_captures_raw_event_id():
    def handler(request):
        return httpx.Response(200, json={
            "record": {"id": "re-123"}, "is_duplicate": False, "enqueued_msg_id": "1-0",
        })
    w = BackendApiRawEventsWriter(client=_client(handler))
    assert w(_CREATE) is True
    assert w.created == 1
    r = w.results[-1]
    assert r.status == contracts.WRITE_CREATED
    assert r.raw_event_id == "re-123"
    assert r.enqueued_msg_id == "1-0"


def test_duplicate_returns_false_collapsed():
    def handler(request):
        return httpx.Response(200, json={
            "record": {"id": "re-123"}, "is_duplicate": True, "enqueued_msg_id": None,
        })
    w = BackendApiRawEventsWriter(client=_client(handler))
    assert w(_CREATE) is False
    assert w.duplicates == 1
    assert w.results[-1].status == contracts.WRITE_DUPLICATE_COLLAPSED


def test_server_error_raises_for_bridge_failed_accounting():
    def handler(request):
        return httpx.Response(503, text="unavailable")
    w = BackendApiRawEventsWriter(client=_client(handler))
    with pytest.raises(RuntimeError):
        w(_CREATE)
    assert w.failed == 1
    assert w.results[-1].status == contracts.WRITE_FAILED_TRANSPORT


def test_client_error_classified_schema():
    def handler(request):
        return httpx.Response(422, text="validation error")
    w = BackendApiRawEventsWriter(client=_client(handler))
    with pytest.raises(RuntimeError):
        w(_CREATE)
    assert w.results[-1].status == contracts.WRITE_FAILED_SCHEMA


def test_transport_error_is_retryable_classification():
    def handler(request):
        raise httpx.ConnectError("connection refused")
    w = BackendApiRawEventsWriter(client=_client(handler))
    r = w.write_raw_event(_CREATE)
    assert r.status == contracts.WRITE_FAILED_TRANSPORT
    assert r.error == "ConnectError"


def test_admin_token_sent_as_header_only(monkeypatch):
    seen = {}

    def handler(request):
        seen["token"] = request.headers.get("X-Admin-Token")
        return httpx.Response(200, json={"record": {"id": "x"}, "is_duplicate": False})
    w = BackendApiRawEventsWriter(client=_client(handler), admin_token="secret-token-value")
    w(_CREATE)
    assert seen["token"] == "secret-token-value"  # 헤더로만 전달


def test_mirror_writer_marked_not_p0_complete(tmp_path):
    w = MirrorRawEventsWriter(tmp_path / "mirror.jsonl")
    assert w(_CREATE) is True
    assert w.summary()["p0_complete_eligible"] is False
