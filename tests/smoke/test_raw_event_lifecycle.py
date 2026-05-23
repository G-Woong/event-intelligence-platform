"""Smoke test: RSS fixture collect → enqueued → processed lifecycle.

Polls GET /api/admin/raw-events/{id} until status="processed" or deadline.
Requires full stack (docker-compose.dev.yml) running.
"""
from __future__ import annotations

import pathlib
import time
import uuid

import httpx
import pytest

_BACKEND = "http://localhost:8000"
_FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
_POLL_TIMEOUT = 60
_POLL_INTERVAL = 2


def _poll_status(raw_event_id: str, target: str, deadline: float = _POLL_TIMEOUT) -> dict | None:
    end = time.time() + deadline
    while time.time() < end:
        try:
            resp = httpx.get(f"{_BACKEND}/api/admin/raw-events/{raw_event_id}", timeout=5)
            if resp.status_code == 200:
                record = resp.json()
                if record["status"] == target:
                    return record
        except Exception:
            pass
        time.sleep(_POLL_INTERVAL)
    return None


@pytest.fixture()
def fixture_sources(monkeypatch):
    file_sources = [
        {
            "name": "bbc_lifecycle_fixture",
            "url": (_FIXTURES / "rss_bbc_min.xml").as_uri(),
            "theme_hint": "geopolitics",
            "enabled": True,
        }
    ]
    import workers.collectors.sources as src_module
    monkeypatch.setattr(src_module, "DEFAULT_SOURCES", file_sources)
    return file_sources


def test_raw_event_lifecycle_reaches_processed(fixture_sources):
    """Collect RSS fixture → find enqueued raw_event → poll until processed."""
    import workers.collectors.rss_collector as collector

    summary = collector.run()
    assert summary["items_seen"] >= 1

    unique_url = f"https://bbc.co.uk/lifecycle-{uuid.uuid4()}"
    payload = {
        "source_type": "rss",
        "source_name": "bbc_lifecycle_fixture",
        "url": unique_url,
        "content_hash": uuid.uuid4().hex * 2,
        "raw_text": "lifecycle smoke test event",
        "raw_metadata": {},
    }
    create_resp = httpx.post(f"{_BACKEND}/api/admin/raw-events", json=payload, timeout=10)
    assert create_resp.status_code == 200
    body = create_resp.json()

    assert body["is_duplicate"] is False
    raw_event_id = body["record"]["id"]
    assert body["record"]["status"] == "enqueued", f"expected enqueued, got {body['record']['status']}"

    record = _poll_status(raw_event_id, "processed", deadline=_POLL_TIMEOUT)
    assert record is not None, (
        f"raw_event {raw_event_id} did not reach status=processed within {_POLL_TIMEOUT}s"
    )
    assert record["event_card_id"] is not None, "processed record should have event_card_id set"
    assert record["processed_at"] is not None, "processed record should have processed_at set"
