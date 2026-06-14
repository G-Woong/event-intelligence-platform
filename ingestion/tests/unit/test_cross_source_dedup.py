"""F-8: Cross-source dedup — 결정적 클러스터링(strong=duplicate, weak=possible)(네트워크 0)."""
from __future__ import annotations

from ingestion.orchestration.cross_source_dedup import (
    cluster_records,
    summarize_clusters,
)


def _rec(**kw):
    base = {
        "record_type": "article_candidate", "source_id": "bbc",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "present",
    }
    base.update(kw)
    return base


def test_same_canonical_across_sources_is_duplicate_cluster():
    recs = [
        _rec(source_id="ap_news", canonical_url="https://wire.test/a", title_or_label="X"),
        _rec(source_id="bbc", canonical_url="https://wire.test/a", title_or_label="X"),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 1
    assert clusters[0].confidence == "duplicate"
    assert len(clusters[0].duplicate_group) == 2


def test_official_id_match_clusters():
    url = "https://www.sec.gov/Archives/edgar/data/1/0000320193-25-000001/0000320193-25-000001-index.htm"
    recs = [
        _rec(record_type="official_record", source_id="sec_edgar", source_url_or_evidence=url, title_or_label="A"),
        _rec(record_type="official_record", source_id="mirror", source_url_or_evidence=url, title_or_label="A"),
    ]
    clusters = cluster_records(recs)
    assert clusters and clusters[0].confidence == "duplicate"


def test_title_date_similarity_is_possible_duplicate():
    recs = [
        _rec(source_id="ap_news", source_url_or_evidence="https://a.test/1",
             canonical_url="https://a.test/1",
             title_or_label="Mars rover finds water ice deposit", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", source_url_or_evidence="https://b.test/2",
             canonical_url="https://b.test/2",
             title_or_label="Mars rover finds water ice deposit", published_at_or_observed_at="2025-06-02"),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 1
    # canonical이 다르므로 strong이 아님 → possible_duplicate (hold)
    assert clusters[0].confidence == "possible_duplicate"


def test_different_dates_not_clustered():
    recs = [
        _rec(source_id="a", canonical_url="https://a.test/1", title_or_label="Same headline text",
             published_at_or_observed_at="2025-06-02"),
        _rec(source_id="b", canonical_url="https://b.test/2", title_or_label="Same headline text",
             published_at_or_observed_at="2025-06-09"),
    ]
    clusters = cluster_records(recs)
    assert clusters == []  # 날짜 bucket 다름 → 클러스터 없음


def test_unrelated_titles_not_clustered():
    recs = [
        _rec(source_id="a", canonical_url="https://a.test/1", title_or_label="Apple earnings up",
             published_at_or_observed_at="2025-06-02"),
        _rec(source_id="b", canonical_url="https://b.test/2", title_or_label="Volcano erupts in Iceland",
             published_at_or_observed_at="2025-06-02"),
    ]
    assert cluster_records(recs) == []


def test_single_record_no_cluster():
    assert cluster_records([_rec(canonical_url="https://a.test/1")]) == []


def test_summarize_clusters_counts():
    recs = [
        _rec(source_id="a", canonical_url="https://wire.test/a", title_or_label="X"),
        _rec(source_id="b", canonical_url="https://wire.test/a", title_or_label="X"),
        _rec(source_id="c", canonical_url="https://c.test/3", title_or_label="Y"),
    ]
    s = summarize_clusters(cluster_records(recs))
    assert s["clusters"] == 1
    assert s["duplicate_clusters"] == 1
    assert s["records_collapsed"] == 1
