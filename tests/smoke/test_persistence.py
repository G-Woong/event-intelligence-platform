"""
Persistence smoke test:
  raw_event → pipeline → FinalEventCard stored in PG
  → backend restart → card survives

사전조건: docker-compose.dev.yml 전체 스택 가동 중.
"""
from __future__ import annotations

import subprocess
import time

import httpx
from datetime import datetime

from workers.queue.producer import enqueue_raw_event
from backend.app.schemas.events import RawEvent

BACKEND = "http://localhost:8000"
PIPELINE_WAIT = 15
POLL_TIMEOUT = 30
POLL_INTERVAL = 2


def _poll_events(timeout: int = POLL_TIMEOUT) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{BACKEND}/api/events", timeout=5.0)
            if resp.status_code == 200:
                cards = resp.json()
                if cards:
                    return cards
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return []


def _poll_health_postgres(timeout: int = POLL_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{BACKEND}/health", timeout=5.0)
            if resp.status_code == 200 and resp.json().get("postgres") == "ok":
                return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return False


def test_persistence_after_restart():
    raw = RawEvent(
        source="persistence-test",
        url="https://example.com/persistence",
        fetched_at=datetime.utcnow(),
        raw_text="Persistence test event: DB survives restart at " + str(time.time()),
        raw_metadata={"env": "persistence"},
    )

    msg_id = enqueue_raw_event(raw)
    print(f"[persistence] enqueued msg_id={msg_id}")

    print(f"[persistence] waiting {PIPELINE_WAIT}s for pipeline...")
    time.sleep(PIPELINE_WAIT)

    cards = _poll_events()
    assert len(cards) > 0, "No FinalEventCards found after pipeline — cannot test persistence"

    target = cards[0]
    target_id = target["id"]
    print(f"[persistence] captured card id={target_id} title={target['title'][:60]}")

    print("[persistence] restarting backend container...")
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.dev.yml", "restart", "backend"],
        check=True,
    )

    print("[persistence] waiting for backend to recover with postgres:ok...")
    assert _poll_health_postgres(), "backend did not recover postgres:ok within timeout"

    resp = httpx.get(f"{BACKEND}/api/events/{target_id}", timeout=10.0)
    assert resp.status_code == 200, f"GET /api/events/{target_id} returned {resp.status_code}"

    restored = resp.json()
    assert restored["id"] == target["id"]
    assert restored["title"] == target["title"]
    assert restored["summary"] == target["summary"]
    assert restored["theme"] == target["theme"]
    assert restored["status"] == target["status"]
    print(f"[persistence] PASS - card survived backend restart: id={target_id}")


if __name__ == "__main__":
    test_persistence_after_restart()
