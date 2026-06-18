from __future__ import annotations

"""P0 하드닝 Phase 3: DLQ 라우팅 + PEL reaper (네트워크 0, FakeRedis)."""

from workers.queue import dlq


class FakeRedis:
    """xadd/xack/xautoclaim 최소 구현. PEL = delivered-but-unacked 모델."""

    def __init__(self):
        self.streams: dict[str, list[tuple[str, dict]]] = {}
        self.pending: dict[tuple[str, str], dict[str, dict]] = {}
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"{self._seq}-0"

    def xadd(self, stream: str, fields: dict) -> str:
        mid = self._next_id()
        self.streams.setdefault(stream, []).append((mid, dict(fields)))
        return mid

    def xack(self, stream: str, group: str, *ids: str) -> int:
        pel = self.pending.setdefault((stream, group), {})
        n = 0
        for i in ids:
            if i in pel:
                del pel[i]
                n += 1
        return n

    def xautoclaim(self, stream, group, consumer, min_idle_time, start_id="0-0", count=100):
        pel = self.pending.get((stream, group), {})
        claimed = [(mid, dict(f)) for mid, f in pel.items()]
        return ("0-0", claimed, [])

    # 테스트 보조: PEL에 stale pending 주입
    def seed_pending(self, stream: str, group: str, fields: dict) -> str:
        mid = self._next_id()
        self.pending.setdefault((stream, group), {})[mid] = dict(fields)
        return mid


_STREAM = "stream:raw_events"
_GROUP = "group:ingest"
_DLQ = "stream:raw_events:dlq"


def test_route_failure_under_max_retries_requeues_and_acks():
    r = FakeRedis()
    mid = r.seed_pending(_STREAM, _GROUP, {"raw_event_id": "abc", "url": "https://x/y"})
    outcome = dlq.route_failure(r, _STREAM, _GROUP, mid, {"raw_event_id": "abc"}, "boom", _DLQ, max_retries=3)
    assert outcome == "retried"
    # 원본 ack됨 (PEL 비움)
    assert mid not in r.pending[(_STREAM, _GROUP)]
    # 동일 스트림에 retry 사본(_retry_count=1) 재발행
    assert len(r.streams[_STREAM]) == 1
    _, fields = r.streams[_STREAM][0]
    assert fields[dlq.RETRY_FIELD] == "1"
    # DLQ로는 안 감
    assert _DLQ not in r.streams


def test_route_failure_at_max_retries_dead_letters():
    r = FakeRedis()
    mid = r.seed_pending(_STREAM, _GROUP, {"raw_event_id": "abc"})
    fields = {"raw_event_id": "abc", dlq.RETRY_FIELD: "3"}
    outcome = dlq.route_failure(r, _STREAM, _GROUP, mid, fields, "poison", _DLQ, max_retries=3)
    assert outcome == "dead_lettered"
    assert mid not in r.pending[(_STREAM, _GROUP)]
    assert len(r.streams[_DLQ]) == 1
    _, dlq_fields = r.streams[_DLQ][0]
    assert dlq_fields[dlq.DLQ_REASON_FIELD] == "poison"
    assert dlq_fields[dlq.DLQ_ORIGINAL_ID_FIELD] == mid
    assert dlq_fields[dlq.DLQ_SOURCE_STREAM_FIELD] == _STREAM
    assert dlq_fields["raw_event_id"] == "abc"
    # retry로는 안 감
    assert _STREAM not in r.streams


def test_no_silent_drop_original_always_acked():
    r = FakeRedis()
    m1 = r.seed_pending(_STREAM, _GROUP, {"raw_event_id": "1"})
    m2 = r.seed_pending(_STREAM, _GROUP, {"raw_event_id": "2", dlq.RETRY_FIELD: "5"})
    dlq.route_failure(r, _STREAM, _GROUP, m1, {"raw_event_id": "1"}, "e", _DLQ, max_retries=3)
    dlq.route_failure(r, _STREAM, _GROUP, m2, {"raw_event_id": "2", dlq.RETRY_FIELD: "5"}, "e", _DLQ, max_retries=3)
    # 둘 다 PEL에서 제거(미ack 잔류 없음)
    assert r.pending[(_STREAM, _GROUP)] == {}


def test_reap_pending_retries_fresh_message():
    r = FakeRedis()
    r.seed_pending(_STREAM, _GROUP, {"raw_event_id": "x", "url": "https://a/b"})
    stats = dlq.reap_pending(r, _STREAM, _GROUP, "reaper-1", 60000, _DLQ, max_retries=3)
    assert stats == {"claimed": 1, "retried": 1, "dead_lettered": 0}
    assert r.pending[(_STREAM, _GROUP)] == {}
    assert len(r.streams[_STREAM]) == 1


def test_reap_pending_dead_letters_exhausted():
    r = FakeRedis()
    r.seed_pending(_STREAM, _GROUP, {"raw_event_id": "x", dlq.RETRY_FIELD: "3"})
    stats = dlq.reap_pending(r, _STREAM, _GROUP, "reaper-1", 60000, _DLQ, max_retries=3)
    assert stats == {"claimed": 1, "retried": 0, "dead_lettered": 1}
    assert len(r.streams[_DLQ]) == 1


def test_reap_pending_empty_pel_noop():
    r = FakeRedis()
    stats = dlq.reap_pending(r, _STREAM, _GROUP, "reaper-1", 60000, _DLQ)
    assert stats == {"claimed": 0, "retried": 0, "dead_lettered": 0}


def test_retry_count_non_integer_treated_as_zero():
    r = FakeRedis()
    mid = r.seed_pending(_STREAM, _GROUP, {"raw_event_id": "x"})
    outcome = dlq.route_failure(
        r, _STREAM, _GROUP, mid, {"raw_event_id": "x", dlq.RETRY_FIELD: "bad"}, "e", _DLQ, max_retries=3
    )
    assert outcome == "retried"
