"""Smoke test: INSERT enqueued raw_event → reconcile-stuck → status=failed.

Requires full stack (docker-compose.dev.yml) running.
Uses PATCH to force status back to "enqueued" after pipeline processes it,
then calls reconcile-stuck to verify the endpoint marks stuck rows as failed.
"""
from __future__ import annotations

import time
import uuid

import httpx
import pytest

_BACKEND = "http://localhost:8000"
_POLL_TIMEOUT = 60
_POLL_INTERVAL = 2


def _poll_status(raw_event_id: str, *targets: str, deadline: float = _POLL_TIMEOUT) -> dict | None:
    end = time.time() + deadline
    while time.time() < end:
        try:
            resp = httpx.get(f"{_BACKEND}/api/admin/raw-events/{raw_event_id}", timeout=5)
            if resp.status_code == 200 and resp.json()["status"] in targets:
                return resp.json()
        except Exception:
            pass
        time.sleep(_POLL_INTERVAL)
    return None


def test_reconciler_marks_stuck_enqueued_as_failed():
    # 1. Create a raw_event — pipeline will set status=enqueued or failed at creation
    unique_hash = uuid.uuid4().hex * 2
    create_resp = httpx.post(
        f"{_BACKEND}/api/admin/raw-events",
        json={
            "source_type": "rss",
            "source_name": "reconciler_smoke",
            "url": f"https://smoke.test/reconciler/{uuid.uuid4()}",
            "content_hash": unique_hash,
            "raw_text": "reconciler smoke test",
            "raw_metadata": {},
        },
        timeout=10,
    )
    assert create_resp.status_code == 200, f"create failed: {create_resp.text}"
    body = create_resp.json()
    assert body["is_duplicate"] is False
    raw_event_id = body["record"]["id"]

    # 2. Wait for pipeline to settle (processed/failed) or stay enqueued if workers down
    settled = _poll_status(raw_event_id, "processed", "failed", "enqueued", deadline=30)
    assert settled is not None, "row should be readable"

    # 3. Force status back to "enqueued" to simulate a stuck row
    patch_resp = httpx.patch(
        f"{_BACKEND}/api/admin/raw-events/{raw_event_id}/status",
        json={"status": "enqueued", "error_reason": None},
        timeout=5,
    )
    assert patch_resp.status_code == 200

    # 4. Wait so updated_at is older than before_seconds=2
    time.sleep(3)

    # 5. Call reconcile-stuck (dry_run=false, before_seconds=2)
    reconcile_resp = httpx.post(
        f"{_BACKEND}/api/admin/raw-events/reconcile-stuck",
        json={"dry_run": False, "before_seconds": 2, "limit": 100},
        timeout=10,
    )
    assert reconcile_resp.status_code == 200, f"reconcile failed: {reconcile_resp.text}"
    r_body = reconcile_resp.json()
    assert r_body["dry_run"] is False
    assert r_body["stuck_count"] >= 1, "expected at least one stuck row"
    assert r_body["marked_failed"] >= 1, "expected at least one row marked as failed"

    # 6. Verify the row is now failed (poll with short window, reconcile just ran)
    record = _poll_status(raw_event_id, "failed", deadline=10)
    assert record is not None, (
        f"raw_event {raw_event_id} did not reach status=failed within 10s"
    )
    assert record["error_reason"] is not None
