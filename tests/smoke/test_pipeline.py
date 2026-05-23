"""
End-to-end smoke test:
  producer → Redis Stream → worker → agent-worker → GET /api/events

사전조건: docker-compose.dev.yml의 backend/worker/agent-worker 가동 중.
"""
from __future__ import annotations

import time
import httpx
from datetime import datetime
from workers.queue.producer import enqueue_raw_event
from backend.app.schemas.events import RawEvent

BACKEND = "http://localhost:8000"
WAIT_SEC = 12


def test_end_to_end():
    raw = RawEvent(
        source="smoke-test",
        url="https://example.com/smoke",
        fetched_at=datetime.utcnow(),
        raw_text="Smoke test event: tensions escalate in test region at " + str(time.time()),
        raw_metadata={"env": "smoke"},
    )

    msg_id = enqueue_raw_event(raw)
    print(f"[smoke] enqueued msg_id={msg_id}")

    print(f"[smoke] waiting {WAIT_SEC}s for pipeline...")
    time.sleep(WAIT_SEC)

    resp = httpx.get(f"{BACKEND}/api/events", timeout=10.0)
    assert resp.status_code == 200, f"GET /api/events returned {resp.status_code}"
    cards = resp.json()
    assert len(cards) > 0, "No FinalEventCards found — pipeline may not have completed"
    print(f"[smoke] PASS - {len(cards)} card(s) found")
    for c in cards:
        print(f"  id={c['id']} title={c['title'][:60]} status={c['status']}")


if __name__ == "__main__":
    test_end_to_end()
