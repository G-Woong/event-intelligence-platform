"""P0: Redis publish — EventQueue Redis Stream roundtrip(FakeRedis) + stream payload 계약(네트워크 0).

A측 EventQueue 의 Redis 백엔드(_redis_*)를 주입형 FakeRedis 로 검증한다. 실 Redis 불필요.
downstream(stream:raw_events) payload 계약은 producer 와 동일 키셋임을 확인한다.
"""
from __future__ import annotations

import json

import pytest

from ingestion.integration import downstream_contracts as contracts
from ingestion.pipeline.event_queue import EventQueue


class FakeRedis:
    """최소 Redis Stream + consumer group 모사(xadd/xgroup_create/xreadgroup/xrange/xack)."""

    def __init__(self):
        self.stream: list[tuple[str, dict]] = []
        self.counter = 0
        self.group_cursor: dict[str, int] = {}
        self.pending: dict[str, set] = {}

    def xadd(self, stream, fields):
        self.counter += 1
        mid = f"{self.counter}-0"
        self.stream.append((mid, dict(fields)))
        return mid

    def xgroup_create(self, stream, group, id="0", mkstream=True):
        if group in self.group_cursor:
            raise Exception("BUSYGROUP Consumer Group name already exists")
        self.group_cursor[group] = 0
        self.pending[group] = set()

    def xreadgroup(self, groupname, consumername, streams, count, block):
        idx = self.group_cursor.get(groupname, 0)
        items = self.stream[idx: idx + count]
        self.group_cursor[groupname] = idx + len(items)
        for mid, _ in items:
            self.pending[groupname].add(mid)
        if not items:
            return []
        stream_name = next(iter(streams.keys()))
        return [(stream_name, items)]

    def xrange(self, stream, count=None):
        return self.stream[:count] if count else list(self.stream)

    def xack(self, stream, group, mid):
        self.pending.get(group, set()).discard(mid)
        return 1


def test_eventqueue_redis_enqueue_dequeue_roundtrip():
    fake = FakeRedis()
    q = EventQueue(redis_client=fake)
    item = {"record_type": "article_candidate", "source_id": "bbc", "title": "t"}
    mid = q.enqueue(item)
    assert mid == "1-0"

    got = q.dequeue(count=5)
    assert len(got) == 1
    assert got[0]["_id"] == "1-0"
    assert got[0]["_status"] == "processing"
    assert got[0]["source_id"] == "bbc"
    # PEL 에 pending 등록
    assert "1-0" in fake.pending["group:ingestion"]


def test_eventqueue_redis_peek_does_not_consume():
    fake = FakeRedis()
    q = EventQueue(redis_client=fake)
    q.enqueue({"source_id": "a"})
    peeked = q.peek(count=5)
    assert len(peeked) == 1 and peeked[0]["_status"] == "pending"
    # peek 후에도 dequeue 가능(소비 안 됨)
    assert len(q.dequeue(count=1)) == 1


def test_eventqueue_redis_mark_done_acks_pel():
    fake = FakeRedis()
    q = EventQueue(redis_client=fake)
    q.enqueue({"source_id": "a"})
    got = q.dequeue(count=1)
    mid = got[0]["_id"]
    assert mid in fake.pending["group:ingestion"]
    q.mark_done(mid)
    assert mid not in fake.pending["group:ingestion"]


def test_eventqueue_redis_dequeue_does_not_redeliver():
    fake = FakeRedis()
    q = EventQueue(redis_client=fake)
    q.enqueue({"source_id": "a"})
    assert len(q.dequeue(count=10)) == 1
    # 이미 전달된 메시지는 '>' 로 재전달되지 않음
    assert q.dequeue(count=10) == []


def test_jsonl_mode_when_no_redis(tmp_path):
    # redis_url="" 이면 명시적 JSONL 전용(Redis 의존 없음)
    q = EventQueue(redis_url="", fallback_dir=tmp_path)
    mid = q.enqueue({"source_id": "a"})
    assert isinstance(mid, str)
    assert len(q.peek()) == 1


def test_stream_payload_contract_matches_producer():
    # downstream worker 가 소비하는 stream:raw_events payload 계약(producer 와 동일 키셋)
    payload = {
        "source": "rss:bbc", "url": "https://x", "fetched_at": "2026-06-17T00:00:00Z",
        "raw_text": "", "raw_metadata": json.dumps({"record_type": "article_candidate"}),
        "raw_event_id": "re-1",
    }
    ok, missing = contracts.validate_stream_payload(payload)
    assert ok, missing


def test_stream_payload_missing_keys_detected():
    ok, missing = contracts.validate_stream_payload({"source": "x"})
    assert not ok
    assert "raw_event_id" in missing
