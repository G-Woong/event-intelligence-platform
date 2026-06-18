"""P0: source 특성(record_type)별 RawEventCreate 매핑 + 계약 검증(네트워크 0).

article/official/structured/community/search 5종이 각각 올바른 source_type + 필수 필드로
매핑되는지, generic text 로 뭉개지지 않는지 검증한다.
"""
from __future__ import annotations

from ingestion.integration import downstream_contracts as contracts
from ingestion.orchestration.bridge_to_raw_events import map_eq_record_to_raw_event


def _rec(record_type, source_id, **kw):
    base = {
        "record_type": record_type,
        "source_id": source_id,
        "title_or_label": f"{source_id} headline",
        "source_url_or_evidence": "https://example.test/a",
        "canonical_url": "https://example.test/a",
        "published_at_or_observed_at": "2026-06-17T00:00:00Z",
        "body_state_or_signal": "present",
        "confirmation_policy": "standard",
        "quality_pre_gate_decision": "accept",
    }
    base.update(kw)
    return base


def _create(record_type, source_id, **kw):
    payload, status, reason = map_eq_record_to_raw_event(_rec(record_type, source_id, **kw))
    assert status == "ok", reason
    return payload.to_raw_event_create()


def test_article_candidate_mapping():
    c = _create("article_candidate", "the_verge")
    assert c["source_type"] == "article"
    ok, missing = contracts.validate_raw_event_create(c, "article_candidate")
    assert ok, missing


def test_official_record_mapping():
    c = _create("official_record", "sec_edgar")
    assert c["source_type"] == "official"
    ok, missing = contracts.validate_raw_event_create(c, "official_record")
    assert ok, missing


def test_structured_signal_mapping():
    c = _create("structured_signal", "coinbase_market", body_state_or_signal="price")
    assert c["source_type"] == "signal"
    # structured_payload 가 raw_metadata 에 실려야 한다(signal_type)
    assert c["raw_metadata"]["structured_payload"] is not None
    ok, missing = contracts.validate_raw_event_create(c, "structured_signal")
    assert ok, missing


def test_community_signal_mapping():
    c = _create("community_signal", "product_hunt",
                confirmation_policy="unconfirmed_until_corroborated")
    assert c["source_type"] == "community"
    assert c["raw_metadata"]["confirmation_policy"] == "unconfirmed_until_corroborated"
    ok, missing = contracts.validate_raw_event_create(c, "community_signal")
    assert ok, missing


def test_search_result_mapping():
    c = _create("search_result", "gnews", body_state_or_signal="snippet")
    assert c["source_type"] == "search"
    ok, missing = contracts.validate_raw_event_create(c, "search_result")
    assert ok, missing


def test_missing_source_url_is_held_not_invented():
    payload, status, reason = map_eq_record_to_raw_event(
        _rec("article_candidate", "x", source_url_or_evidence=None, canonical_url=None)
    )
    assert payload is None
    assert status == "held"
    assert reason == "missing_external_url"


def test_content_hash_is_sha256_64hex():
    c = _create("article_candidate", "ap_news")
    h = c["content_hash"]
    assert len(h) == 64
    assert all(ch in "0123456789abcdef" for ch in h)


def test_raw_text_is_empty_preview_only():
    # 전문(full body)은 raw_text 에 공개 저장하지 않는다(§14 preview_only).
    for rt, sid in [("article_candidate", "bbc"), ("community_signal", "dcinside")]:
        c = _create(rt, sid)
        assert c["raw_text"] == ""


def test_source_type_mismatch_is_flagged():
    c = _create("article_candidate", "ap_news")
    c["source_type"] = "signal"  # 둔갑
    ok, missing = contracts.validate_raw_event_create(c, "article_candidate")
    assert not ok
    assert any("source_type" in m for m in missing)
