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


def test_full_strong_clique_ok():
    # 3소스가 같은 canonical → 전원 강신호 anchor → clique_ok, signal_strength=1.0.
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x", title_or_label="X"),
        _rec(source_id="bbc", canonical_url="https://wire/x", title_or_label="X"),
        _rec(source_id="cnn", canonical_url="https://wire/x", title_or_label="X"),
    ]
    c = cluster_records(recs)[0]
    assert c.confidence == "duplicate"
    assert c.clique_ok is True
    assert c.weak_only_members == ()
    assert c.signal_strength == 1.0


def test_transitive_false_merge_flagged_by_clique_gate():
    # R-FalseMerge(adversarial #1): ap-reuters 강신호(canonical), blog는 title만 일치(약신호).
    # Union-Find는 셋을 한 클러스터로 묶지만, blog는 강신호 anchor가 없으므로 clique_ok=False
    # → resolver가 자동 APPEND하지 않고 blog를 HOLD해야 한다(transitive 흡수 차단).
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="reuters", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="blog", canonical_url="https://blog/z",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.confidence == "duplicate"        # 강신호 존재(ap-reuters)
    assert c.clique_ok is False               # 그러나 blog는 약신호-only
    assert len(c.weak_only_members) == 1      # blog 1건이 clique 미달(HOLD 후보)


def test_two_strong_components_bridged_by_weak_is_not_clique():
    # R-FalseMerge B1(adversarial 교정): 두 개의 분리된 강성분(ap-reuters / afp-dpa)이
    # 동일 제목(약신호)으로만 브릿지된다. "강신호 끝점인가"만 보면 전원 anchor라 오통과하지만,
    # 강신호 단일 연결성분 기준이면 강성분이 2개 → clique 미달(비-primary 성분 보류).
    title = "hormuz strait tanker seized by navy"
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(source_id="reuters", canonical_url="https://wire/x", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(source_id="afp", canonical_url="https://other/y", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(source_id="dpa", canonical_url="https://other/y", title_or_label=title, published_at_or_observed_at="2025-06-02"),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.confidence == "duplicate"        # 강신호 존재
    assert c.clique_ok is False               # 두 강성분이 약신호로만 브릿지 → clique 미달
    assert len(c.weak_only_members) == 2      # 비-primary 강성분(afp,dpa) 분리 보류


def test_weak_cluster_preserves_continuous_signal_strength():
    # 약신호-only 클러스터: Jaccard 연속값 보존(1비트 양자화 폐기, orchestrator #2).
    recs = [
        _rec(source_id="a", canonical_url="https://a/1",
             title_or_label="mars rover finds water ice deposit today",
             published_at_or_observed_at="2025-06-02"),
        _rec(source_id="b", canonical_url="https://b/2",
             title_or_label="mars rover finds water ice deposit",
             published_at_or_observed_at="2025-06-02"),
    ]
    c = cluster_records(recs)[0]
    assert c.confidence == "possible_duplicate"
    assert c.clique_ok is False               # 강신호 0 → 전원 weak-only
    assert 0.8 <= c.signal_strength < 1.0     # 연속값(≈0.857), 1.0으로 양자화되지 않음


def test_titles_similar_contract():
    # ADR#38 held 승격 판정자: 정규화 일치 OR token Jaccard≥0.8 → 같은 사건.
    from ingestion.orchestration.cross_source_dedup import titles_similar
    assert titles_similar("Bank collapse triggers selloff", "bank collapse triggers selloff")   # 정규화 일치
    assert titles_similar("Major outage hits cloud provider today",
                          "Major outage hits cloud provider")                                   # Jaccard≈0.83
    assert not titles_similar("Bank collapse triggers selloff", "Unrelated weather storm warning")
    assert not titles_similar("", "anything")                                                   # 빈 입력=False
    assert not titles_similar(None, "x")


def test_legacy_fields_unchanged_additive():
    # 기존 소비처 비파괴: confidence/duplicate_group 등 기존 필드 동작 불변.
    recs = [
        _rec(source_id="a", canonical_url="https://wire.test/a", title_or_label="X"),
        _rec(source_id="b", canonical_url="https://wire.test/a", title_or_label="X"),
    ]
    c = cluster_records(recs)[0]
    assert c.confidence == "duplicate"
    assert len(c.duplicate_group) == 2
    assert c.reason == "strong_key_match"


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
