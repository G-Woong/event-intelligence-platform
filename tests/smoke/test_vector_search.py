from __future__ import annotations

import os
import time

import pytest
import httpx

from workers.queue.producer import enqueue_raw_event
from backend.app.schemas.events import RawEvent

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
RUN_MILVUS = os.getenv("RUN_MILVUS_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_MILVUS,
    reason="RUN_MILVUS_INTEGRATION not set",
)

WAIT_SEC = 15


def test_vector_search_e2e():
    raw = RawEvent(
        source="smoke-vector",
        url="http://example.com/smoke-vector",
        raw_text="Major flood in southern region causes widespread evacuation and damage.",
        raw_metadata={"env": "smoke"},
    )
    msg_id = enqueue_raw_event(raw)
    print(f"[smoke-vector] enqueued msg_id={msg_id}")

    print(f"[smoke-vector] waiting {WAIT_SEC}s for pipeline...")
    time.sleep(WAIT_SEC)

    events_resp = httpx.get(f"{BACKEND_URL}/api/events", timeout=10)
    assert events_resp.status_code == 200
    items = events_resp.json()
    assert len(items) > 0, "no cards found after pipeline"
    card_id = items[0]["id"]
    print(f"[smoke-vector] card_id={card_id}")

    search_resp = httpx.post(
        f"{BACKEND_URL}/api/internal/search-similar",
        json={"query_text": "flood evacuation disaster", "top_k": 5},
        timeout=10,
    )
    assert search_resp.status_code == 200
    body = search_resp.json()
    print(f"[smoke-vector] hits={body['hits']}")
    hit_ids = [h["event_id"] for h in body["hits"]]
    assert card_id in hit_ids, f"expected {card_id} in hits {hit_ids}"
    print(f"[smoke-vector] PASS top1.event_id={hit_ids[0] if hit_ids else 'none'}")
