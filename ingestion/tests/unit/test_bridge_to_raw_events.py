"""F-10: raw_events bridge — record_type 변환 + 중복 skip + url 없으면 hold + mirror(네트워크 0)."""
from __future__ import annotations

import json

from ingestion.orchestration.bridge_to_raw_events import (
    BRIDGE_STATUS_HELD,
    BRIDGE_STATUS_REJECTED,
    BRIDGE_STATUS_WRITTEN,
    RawEventBridgeWriter,
    bridge_records,
    map_eq_record_to_raw_event,
)


def _rec(**kw):
    base = {
        "record_type": "article_candidate", "source_id": "ap_news",
        "title_or_label": "Headline", "source_url_or_evidence": "https://ap.test/a",
        "canonical_url": "https://ap.test/a", "published_at_or_observed_at": "2025-06-02T10:00:00Z",
        "body_state_or_signal": "present", "confirmation_policy": "source_confirmed",
        "quality_pre_gate_decision": "pass",
    }
    base.update(kw)
    return base


def test_article_candidate_maps_to_raw_event():
    payload, status, reason = map_eq_record_to_raw_event(_rec())
    assert status == "ok" and payload is not None
    rc = payload.to_raw_event_create()
    assert rc["source_type"] == "article"
    assert rc["url"] == "https://ap.test/a"
    assert len(rc["content_hash"]) == 64
    assert rc["raw_text"] == ""  # 전문 미포함(preview_only)


def test_official_record_maps_source_type_official():
    payload, status, _ = map_eq_record_to_raw_event(
        _rec(record_type="official_record", source_id="sec_edgar"))
    assert payload.to_raw_event_create()["source_type"] == "official"


def test_structured_signal_maps_signal_with_payload():
    payload, status, _ = map_eq_record_to_raw_event(
        _rec(record_type="structured_signal", source_id="twelve_data",
             body_state_or_signal="numeric"))
    rc = payload.to_raw_event_create()
    assert rc["source_type"] == "signal"
    assert rc["raw_metadata"]["structured_payload"]["signal_type"] == "numeric"


def test_search_and_community_record_types():
    p1, _, _ = map_eq_record_to_raw_event(_rec(record_type="search_result", source_id="serper"))
    p2, _, _ = map_eq_record_to_raw_event(_rec(record_type="community_signal", source_id="youtube"))
    assert p1.to_raw_event_create()["source_type"] == "search"
    assert p2.to_raw_event_create()["source_type"] == "community"


def test_missing_url_is_held_not_written():
    payload, status, reason = map_eq_record_to_raw_event(
        _rec(source_url_or_evidence="local/path.json", canonical_url=None))
    assert payload is None
    assert status == BRIDGE_STATUS_HELD and reason == "missing_external_url"


def test_invalid_record_type_rejected():
    payload, status, reason = map_eq_record_to_raw_event(_rec(record_type="bogus"))
    assert payload is None and status == BRIDGE_STATUS_REJECTED


def test_date_only_precision_preserved_in_metadata():
    payload, _, _ = map_eq_record_to_raw_event(_rec(published_at_or_observed_at="2025-06-02"))
    assert payload.published_precision == "date"


def test_mirror_writer_writes_jsonl(tmp_path):
    mirror = tmp_path / "raw_events_mirror.jsonl"
    w = RawEventBridgeWriter(mirror_path=mirror)
    payload, _, _ = map_eq_record_to_raw_event(_rec())
    assert w.write(payload) == BRIDGE_STATUS_WRITTEN
    lines = mirror.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["url"] == "https://ap.test/a"


def test_duplicate_content_hash_skipped():
    w = RawEventBridgeWriter()
    payload, _, _ = map_eq_record_to_raw_event(_rec())
    assert w.write(payload) == BRIDGE_STATUS_WRITTEN
    payload2, _, _ = map_eq_record_to_raw_event(_rec())  # 같은 canonical → 같은 content_hash
    assert w.write(payload2) == "duplicate_skipped"


def test_db_unavailable_falls_back_to_mirror(tmp_path):
    # db_writer 미지정 → target=mirror
    w = RawEventBridgeWriter(mirror_path=tmp_path / "m.jsonl", db_writer=None)
    assert w.target == "mirror"


def test_db_writer_used_when_provided():
    captured = []
    w = RawEventBridgeWriter(db_writer=lambda d: captured.append(d) or True)
    payload, _, _ = map_eq_record_to_raw_event(_rec())
    assert w.write(payload) == BRIDGE_STATUS_WRITTEN
    assert w.target == "db" and len(captured) == 1
    assert "content_hash" in captured[0]


def test_db_writer_conflict_returns_duplicate():
    # db_writer가 False 반환(on_conflict_do_nothing) → duplicate로 집계
    w = RawEventBridgeWriter(db_writer=lambda d: False)
    payload, _, _ = map_eq_record_to_raw_event(_rec())
    assert w.write(payload) == "duplicate_skipped"


def test_bridge_records_contract_pass(tmp_path):
    recs = [_rec(canonical_url="https://a.test/1", source_url_or_evidence="https://a.test/1"),
            _rec(canonical_url="https://a.test/2", source_url_or_evidence="https://a.test/2", source_id="bbc")]
    w = RawEventBridgeWriter(mirror_path=tmp_path / "m.jsonl")
    result = bridge_records(recs, writer=w)
    assert result["raw_events_written"] == 2
    assert result["bridge_contract_pass"] is True
    assert result["schema_failures"] == 0


def test_bridge_records_holds_missing_url(tmp_path):
    recs = [_rec(source_url_or_evidence="local/x.json", canonical_url=None)]
    w = RawEventBridgeWriter(mirror_path=tmp_path / "m.jsonl")
    result = bridge_records(recs, writer=w)
    assert result["raw_events_held"] == 1
    assert result["raw_events_written"] == 0
    # held는 schema 실패가 아님 → contract는 여전히 pass
    assert result["bridge_contract_pass"] is True


def test_write_failure_breaks_contract():
    def boom(d):
        raise RuntimeError("db down")
    w = RawEventBridgeWriter(db_writer=boom)
    recs = [_rec()]
    result = bridge_records(recs, writer=w)
    assert result["raw_events_failed"] == 1
    assert result["bridge_contract_pass"] is False
