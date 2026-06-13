from __future__ import annotations

import pytest

from ingestion.pipeline.canonical_event_builder import CanonicalEventBuilder
from ingestion.pipeline.discovery_collector import DiscoveryCollector
from ingestion.pipeline.event_candidate_extractor import EventCandidateExtractor
from ingestion.pipeline.event_queue import EventQueue
from ingestion.pipeline.query_generator import QueryGenerator
from ingestion.pipeline.search_enrichment_collector import SearchEnrichmentCollector


# ── import sanity ─────────────────────────────────────────────────────────

def test_all_pipeline_modules_importable():
    assert DiscoveryCollector is not None
    assert SearchEnrichmentCollector is not None
    assert EventCandidateExtractor is not None
    assert EventQueue is not None
    assert QueryGenerator is not None
    assert CanonicalEventBuilder is not None


# ── constructor defaults ───────────────────────────────────────────────────

def test_discovery_collector_constructor():
    dc = DiscoveryCollector()
    assert dc.source_ids == []

    dc2 = DiscoveryCollector(source_ids=["bbc", "yna"])
    assert dc2.source_ids == ["bbc", "yna"]


def test_search_enrichment_collector_constructor():
    sec = SearchEnrichmentCollector()
    assert sec.search_source_ids == []


def test_event_candidate_extractor_constructor():
    ece = EventCandidateExtractor(llm_provider="mock")
    assert ece.llm_provider == "mock"


def test_query_generator_constructor():
    qg = QueryGenerator(max_queries_per_candidate=3)
    assert qg.max_queries_per_candidate == 3


def test_canonical_event_builder_constructor():
    ceb = CanonicalEventBuilder()
    assert ceb is not None


# ── stub raises NotImplementedError ───────────────────────────────────────

def test_discovery_collector_collect_raises():
    with pytest.raises(NotImplementedError):
        DiscoveryCollector().collect(["bbc"])


def test_event_candidate_extractor_raises():
    with pytest.raises(NotImplementedError):
        EventCandidateExtractor().extract([{"title": "test"}])


def test_query_generator_raises():
    with pytest.raises(NotImplementedError):
        QueryGenerator().generate({"title": "test"})


def test_canonical_event_builder_raises():
    with pytest.raises(NotImplementedError):
        CanonicalEventBuilder().build([{"title": "test"}])


# ── EventQueue JSONL fallback: minimal live contract ─────────────────────

def test_event_queue_jsonl_enqueue_dequeue(tmp_path):
    # redis_url="" forces JSONL fallback regardless of REDIS_URL env var
    q = EventQueue(redis_url="", fallback_dir=tmp_path)
    item_id = q.enqueue({"title": "test event", "source": "bbc"})
    assert isinstance(item_id, str) and len(item_id) > 0

    items = q.dequeue(count=1)
    assert len(items) == 1
    assert items[0]["title"] == "test event"
    assert items[0]["_id"] == item_id
    assert items[0]["_status"] == "processing"


def test_event_queue_jsonl_mark_done(tmp_path):
    q = EventQueue(redis_url="", fallback_dir=tmp_path)
    item_id = q.enqueue({"title": "done test"})
    q.dequeue(1)
    q.mark_done(item_id)

    # After mark_done, re-dequeue should return nothing (not pending/processing)
    items = q.dequeue(1)
    assert items == []


def test_event_queue_jsonl_peek_does_not_consume(tmp_path):
    q = EventQueue(redis_url="", fallback_dir=tmp_path)
    q.enqueue({"title": "peek test"})
    peeked = q.peek(1)
    assert len(peeked) == 1
    # Item is still pending — dequeue should still return it
    dequeued = q.dequeue(1)
    assert len(dequeued) == 1
    assert dequeued[0]["title"] == "peek test"


def test_event_queue_redis_raises_when_forced(tmp_path):
    q = EventQueue(redis_url="redis://localhost:6379", fallback_dir=tmp_path)
    assert q._use_redis is True
    with pytest.raises(NotImplementedError):
        q.enqueue({"title": "redis test"})
