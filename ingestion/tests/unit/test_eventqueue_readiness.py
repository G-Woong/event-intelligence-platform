"""Phase E-2: EventQueue readiness — record_type/스키마 검증 + REDIS_URL 무관 JSONL 안전."""
from __future__ import annotations

from ingestion.orchestration.full_source_revival import (
    build_eventqueue_record,
    check_eventqueue_readiness,
)
from ingestion.pipeline.event_queue import EventQueue


def _record(**kw):
    base = dict(record_type="article_candidate", source_id="yna",
                title_or_label="제목", source_url_or_evidence="https://x/a",
                canonical_url="https://x/a", published_at_or_observed_at="2026-06-14",
                body_state_or_signal="present", confirmation_policy="standard",
                quality_pre_gate_decision="pass")
    base.update(kw)
    return build_eventqueue_record(**base)


def test_complete_record_is_ready():
    ok, gaps = check_eventqueue_readiness(_record())
    assert ok is True and gaps == ()


def test_missing_title_and_evidence_fails():
    ok, gaps = check_eventqueue_readiness(
        _record(title_or_label=None, source_url_or_evidence=None))
    assert ok is False
    assert "no_title_or_label" in gaps and "no_evidence_ref" in gaps


def test_invalid_record_type_fails():
    ok, gaps = check_eventqueue_readiness(_record(record_type="bogus"))
    assert ok is False and "invalid_record_type" in gaps


def test_official_record_without_date_still_ready():
    # official record는 date_absent 허용(§1.3) — 시간 없어도 ready를 막지 않는다
    ok, gaps = check_eventqueue_readiness(
        _record(record_type="official_record", published_at_or_observed_at=None))
    assert ok is True


def test_structured_signal_record_type_valid():
    ok, _ = check_eventqueue_readiness(
        _record(record_type="structured_signal", title_or_label="BTCUSDT"))
    assert ok is True


def test_jsonl_queue_is_safe_regardless_of_redis_url(tmp_path, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://example:6379")
    # 명시 JSONL(redis_url="")이면 REDIS_URL 환경과 무관하게 JSONL로 안전 동작
    q = EventQueue(redis_url="", fallback_dir=tmp_path)
    item_id = q.enqueue({"record_type": "article_candidate", "source_id": "yna"})
    assert item_id
    peeked = q.peek(5)
    assert peeked and peeked[0]["source_id"] == "yna"
