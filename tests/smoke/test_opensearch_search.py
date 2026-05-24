"""Smoke test: event_card upsert → OpenSearch index → keyword search hit.

Requires RUN_OPENSEARCH_INTEGRATION=1 and a running OpenSearch at localhost:9200.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest

RUN_OS = os.getenv("RUN_OPENSEARCH_INTEGRATION") == "1"
skip_os = pytest.mark.skipif(not RUN_OS, reason="RUN_OPENSEARCH_INTEGRATION not set")


@skip_os
def test_upsert_and_search():
    token = f"STEP009_smoke_token_{uuid.uuid4().hex[:8]}"

    import httpx
    base = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8000")
    admin_token = os.getenv("ADMIN_API_TOKEN", "")
    headers = {"X-Admin-Token": admin_token} if admin_token else {}

    card_payload = {
        "title": token,
        "summary": f"Smoke test card for {token}",
        "theme": "smoke_test",
        "sectors": ["test"],
        "entities": ["smoke"],
        "status": "published",
        "confidence_score": 0.99,
    }
    upsert_resp = httpx.post(f"{base}/api/admin/upsert-event", json=card_payload, headers=headers, timeout=15)
    assert upsert_resp.status_code == 200, upsert_resp.text
    card_id = upsert_resp.json()["id"]

    from opensearchpy import OpenSearch
    os_host = os.getenv("OPENSEARCH_HOST", "localhost")
    os_port = int(os.getenv("OPENSEARCH_PORT", "9200"))
    client = OpenSearch(hosts=[{"host": os_host, "port": os_port}], use_ssl=False)
    client.indices.refresh(index=os.getenv("OPENSEARCH_EVENT_INDEX", "event_cards"))

    search_resp = httpx.get(f"{base}/api/events/search?q={token}", timeout=15)
    assert search_resp.status_code == 200, search_resp.text
    data = search_resp.json()
    assert data["total"] >= 1
    found_ids = [h["card_id"] for h in data["hits"]]
    assert card_id in found_ids
