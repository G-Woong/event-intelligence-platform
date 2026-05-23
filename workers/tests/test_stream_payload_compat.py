from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.app.schemas.events import RawEvent
from workers.queue.producer import enqueue_raw_event
from workers.pipelines.ingest_pipeline import process


def _make_raw(raw_event_id=None) -> RawEvent:
    return RawEvent(
        source="rss:test",
        url="https://example.com/1",
        fetched_at=datetime(2026, 1, 1, 12, 0),
        raw_text="some text",
        raw_metadata={"k": "v"},
        raw_event_id=raw_event_id,
    )


def test_producer_includes_raw_event_id():
    raw = _make_raw(raw_event_id="uuid-abc-123")
    captured = {}

    def fake_xadd(stream, payload):
        captured.update(payload)
        return "1-0"

    with patch("workers.queue.producer.redis_db.xadd", side_effect=fake_xadd):
        enqueue_raw_event(raw)

    assert captured.get("raw_event_id") == "uuid-abc-123"


def test_producer_raw_event_id_none_sends_empty_string():
    raw = _make_raw(raw_event_id=None)
    captured = {}

    def fake_xadd(stream, payload):
        captured.update(payload)
        return "1-0"

    with patch("workers.queue.producer.redis_db.xadd", side_effect=fake_xadd):
        enqueue_raw_event(raw)

    assert captured.get("raw_event_id") == ""


def test_ingest_pipeline_forwards_raw_event_id():
    forwarded = {}

    def fake_xadd(stream, payload):
        forwarded.update(payload)

    fields = {
        "source": "rss:test",
        "url": "https://example.com/1",
        "fetched_at": "2026-01-01T12:00:00",
        "raw_text": "body",
        "raw_metadata": "{}",
        "raw_event_id": "uuid-abc-123",
    }

    with patch("workers.pipelines.ingest_pipeline.redis_db.xadd", side_effect=fake_xadd):
        process("1-0", fields)

    assert forwarded.get("raw_event_id") == "uuid-abc-123"


def test_ingest_pipeline_legacy_payload_no_raw_event_id():
    forwarded = {}

    def fake_xadd(stream, payload):
        forwarded.update(payload)

    fields = {
        "source": "rss:test",
        "url": "https://example.com/1",
        "fetched_at": "2026-01-01T12:00:00",
        "raw_text": "body",
        "raw_metadata": "{}",
    }

    with patch("workers.pipelines.ingest_pipeline.redis_db.xadd", side_effect=fake_xadd):
        process("1-0", fields)

    assert forwarded.get("raw_event_id") == ""


def test_ingest_pipeline_constructs_raw_event_with_none_when_key_absent():
    constructed: list[RawEvent] = []
    original_init = RawEvent.__init__

    fields = {
        "source": "rss:test",
        "url": "https://example.com/1",
        "fetched_at": "2026-01-01T12:00:00",
        "raw_text": "body",
        "raw_metadata": "{}",
    }

    with patch("workers.pipelines.ingest_pipeline.redis_db.xadd"):
        process("1-0", fields)

    raw = RawEvent(
        source=fields["source"],
        url=fields["url"],
        fetched_at=datetime.fromisoformat(fields["fetched_at"]),
        raw_text=fields["raw_text"],
        raw_metadata=json.loads(fields["raw_metadata"]),
        raw_event_id=fields.get("raw_event_id") or None,
    )
    assert raw.raw_event_id is None
