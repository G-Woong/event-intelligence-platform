"""Smoke test: create → fail → requeue → processed lifecycle.

Requires full stack (docker-compose.dev.yml) running.
"""
from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

_BACKEND = "http://localhost:8000"
_POLL_TIMEOUT = 60
_POLL_INTERVAL = 2


def _headers() -> dict[str, str]:
    token = os.getenv("ADMIN_API_TOKEN", "")
    return {"X-Admin-Token": token} if token else {}


def _poll_status(raw_event_id: str, *targets: str, deadline: float = _POLL_TIMEOUT) -> dict | None:
    end = time.time() + deadline
    while time.time() < end:
        try:
            resp = httpx.get(
                f"{_BACKEND}/api/admin/raw-events/{raw_event_id}",
                headers=_headers(),
                timeout=5,
            )
            if resp.status_code == 200 and resp.json()["status"] in targets:
                return resp.json()
        except Exception:
            pass
        time.sleep(_POLL_INTERVAL)
    return None


def test_requeue_lifecycle():
    """create → poll settled → PATCH=failed → requeue → poll processed."""
    unique_hash = uuid.uuid4().hex * 2
    create_resp = httpx.post(
        f"{_BACKEND}/api/admin/raw-events",
        json={
            "source_type": "rss",
            "source_name": "requeue_smoke",
            "url": f"https://smoke.test/requeue/{uuid.uuid4()}",
            "content_hash": unique_hash,
            "raw_text": "requeue smoke test event",
            "raw_metadata": {},
        },
        headers=_headers(),
        timeout=10,
    )
    assert create_resp.status_code == 200, f"create failed: {create_resp.text}"
    body = create_resp.json()
    assert body["is_duplicate"] is False
    raw_event_id = body["record"]["id"]

    settled = _poll_status(raw_event_id, "processed", "failed", "enqueued", deadline=30)
    assert settled is not None, "row should be readable"

    patch_resp = httpx.patch(
        f"{_BACKEND}/api/admin/raw-events/{raw_event_id}/status",
        json={"status": "failed", "error_reason": "smoke: forced fail for requeue test"},
        headers=_headers(),
        timeout=5,
    )
    assert patch_resp.status_code == 200, f"patch failed: {patch_resp.text}"

    requeue_resp = httpx.post(
        f"{_BACKEND}/api/admin/raw-events/{raw_event_id}/requeue",
        json={"force": False},
        headers=_headers(),
        timeout=10,
    )
    assert requeue_resp.status_code == 200, f"requeue failed: {requeue_resp.text}"
    rq_body = requeue_resp.json()
    assert rq_body["enqueued_msg_id"] is not None
    assert rq_body["requeue_count"] >= 1

    final = _poll_status(raw_event_id, "processed", "failed", deadline=_POLL_TIMEOUT)
    assert final is not None, f"raw_event {raw_event_id} did not settle after requeue"
    assert final["raw_metadata"].get("requeue_count", 0) >= 1
