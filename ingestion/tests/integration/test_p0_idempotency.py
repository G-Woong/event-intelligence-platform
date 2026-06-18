"""P0: idempotency — dedup_key/content_hash 일관성 + 재실행 duplicate collapse(네트워크 0).

같은 record 를 두 번 bridge 하면 content_hash 가 동일하고, writer 가 두 번째를 collapse 한다.
"""
from __future__ import annotations

import httpx

from ingestion.integration.raw_events_writer import BackendApiRawEventsWriter
from ingestion.orchestration.bridge_to_raw_events import (
    RawEventBridgeWriter,
    bridge_records,
    map_eq_record_to_raw_event,
)


def _rec(url="https://ap.test/a"):
    return {
        "record_type": "article_candidate", "source_id": "ap_news",
        "title_or_label": "Headline", "source_url_or_evidence": url,
        "canonical_url": url, "published_at_or_observed_at": "2026-06-17T00:00:00Z",
        "body_state_or_signal": "present", "confirmation_policy": "standard",
        "quality_pre_gate_decision": "accept",
    }


def test_content_hash_stable_across_runs():
    p1, _, _ = map_eq_record_to_raw_event(_rec())
    p2, _, _ = map_eq_record_to_raw_event(_rec())
    assert p1.content_hash == p2.content_hash
    assert p1.dedup_key == p2.dedup_key


def test_distinct_urls_distinct_hash():
    p1, _, _ = map_eq_record_to_raw_event(_rec("https://ap.test/a"))
    p2, _, _ = map_eq_record_to_raw_event(_rec("https://ap.test/b"))
    assert p1.content_hash != p2.content_hash


class _BackendState:
    """content_hash on_conflict 모사 — 같은 hash 두 번째는 is_duplicate."""

    def __init__(self):
        self.seen = set()

    def handler(self, request):
        import json
        body = json.loads(request.content)
        h = body["content_hash"]
        dup = h in self.seen
        self.seen.add(h)
        return httpx.Response(200, json={
            "record": {"id": f"re-{h[:6]}"}, "is_duplicate": dup,
            "enqueued_msg_id": None if dup else "1-0",
        })


def test_rerun_collapses_duplicates_via_backend_on_conflict():
    state = _BackendState()
    client = httpx.Client(transport=httpx.MockTransport(state.handler))
    records = [_rec(), _rec()]  # 동일 record 2건

    # 1차 실행
    w1 = BackendApiRawEventsWriter(client=client)
    bw1 = RawEventBridgeWriter(db_writer=w1)
    r1 = bridge_records(records, writer=bw1)
    # bridge 의 in-memory seen_hashes 가 2번째를 먼저 collapse
    assert r1["raw_events_written"] == 1
    assert r1["raw_events_skipped_duplicates"] == 1

    # 2차 실행(재시작 모사: 새 writer → backend on_conflict 가 collapse)
    w2 = BackendApiRawEventsWriter(client=client)
    bw2 = RawEventBridgeWriter(db_writer=w2)
    r2 = bridge_records(records[:1], writer=bw2)
    assert r2["raw_events_written"] == 0
    assert r2["raw_events_skipped_duplicates"] == 1
    assert w2.duplicates == 1
