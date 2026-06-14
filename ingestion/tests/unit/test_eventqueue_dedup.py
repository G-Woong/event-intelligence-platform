"""F-7: EventQueue dedup — record_type별 키 우선순위 + 인덱스 collapse(네트워크 0)."""
from __future__ import annotations

from ingestion.orchestration.eventqueue_dedup import (
    DedupIndex,
    compute_record_key,
    dedup_records,
)


def _rec(**kw):
    base = {
        "record_type": "article_candidate", "source_id": "bbc",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "present",
        "confirmation_policy": "source_confirmed", "quality_pre_gate_decision": "pass",
    }
    base.update(kw)
    return base


def test_canonical_url_priority():
    k, basis = compute_record_key(_rec(canonical_url="https://x.test/a",
                                       source_url_or_evidence="https://x.test/a?utm=1"))
    assert basis == "canonical_url" and k.startswith("canon:")


def test_canonical_url_duplicate_collapse():
    idx = DedupIndex()
    r1 = _rec(canonical_url="https://x.test/a")
    r2 = _rec(canonical_url="https://x.test/a", source_id="ap_news")  # 다른 source 같은 canonical
    d1 = idx.decide(r1, ref="1")
    d2 = idx.decide(r2, ref="2")
    assert d1.is_duplicate is False
    assert d2.is_duplicate is True and d2.existing_ref == "1"


def test_source_url_dedup_when_no_canonical():
    k, basis = compute_record_key(_rec(source_url_or_evidence="https://x.test/b"))
    assert basis == "source_url" and k.startswith("url:")


def test_local_path_not_treated_as_url():
    # 로컬 파일 경로는 외부 URL이 아니므로 source_url 키로 쓰지 않는다(둔갑 금지)
    k, basis = compute_record_key(_rec(source_url_or_evidence="ingestion/outputs/raw/x.json",
                                       title_or_label="t", published_at_or_observed_at="2025-06-02"))
    assert basis == "fallback_title_time"


def test_official_id_accession_dedup():
    url = "https://www.sec.gov/Archives/edgar/data/320193/0000320193-25-000001/0000320193-25-000001-index.htm"
    k, basis = compute_record_key(_rec(record_type="official_record", source_id="sec_edgar",
                                       source_url_or_evidence=url))
    assert basis == "official_id"


def test_structured_signal_key_source_signal_time():
    r = _rec(record_type="structured_signal", source_id="twelve_data",
             body_state_or_signal="numeric", published_at_or_observed_at="2026-06-14T09:00:00Z")
    k, basis = compute_record_key(r)
    assert basis == "signal_key" and k.startswith("signal:")


def test_structured_signal_duplicate_same_timestamp():
    idx = DedupIndex()
    r1 = _rec(record_type="structured_signal", source_id="twelve_data",
              body_state_or_signal="numeric", published_at_or_observed_at="2026-06-14T09:00:00Z")
    r2 = dict(r1)
    assert idx.decide(r1, ref="1").is_duplicate is False
    assert idx.decide(r2, ref="2").is_duplicate is True


def test_search_result_key_title_url():
    r = _rec(record_type="search_result", source_id="serper",
             title_or_label="Result A", source_url_or_evidence="https://x.test/s")
    k, basis = compute_record_key(r)
    assert basis == "search_title_url"


def test_fallback_title_time_when_no_url():
    k, basis = compute_record_key(_rec(title_or_label="Headline", published_at_or_observed_at="2025-06-02"))
    assert basis == "fallback_title_time" and k.startswith("meta:")


def test_no_identifier_returns_none_key():
    k, basis = compute_record_key(_rec())  # title/url/time 전부 없음
    assert k is None and basis is None


def test_no_key_not_duplicate():
    idx = DedupIndex()
    d = idx.decide(_rec(), ref="1")
    assert d.is_duplicate is False and d.reason == "no_dedup_key"


def test_dedup_records_batch_collapses_internal_dupes():
    recs = [_rec(canonical_url="https://x.test/a"),
            _rec(canonical_url="https://x.test/a"),
            _rec(canonical_url="https://x.test/b")]
    out = dedup_records(recs)
    dups = [d.is_duplicate for _, d in out]
    assert dups == [False, True, False]


def test_index_persistence(tmp_path):
    p = tmp_path / "idx.json"
    idx = DedupIndex(path=p)
    idx.decide(_rec(canonical_url="https://x.test/a"), ref="1")
    idx.save()
    idx2 = DedupIndex(path=p)
    assert idx2.decide(_rec(canonical_url="https://x.test/a"), ref="2").is_duplicate is True
