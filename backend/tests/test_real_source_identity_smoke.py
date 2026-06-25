"""ADR#54/#55 — real-source identity smoke 진단 잠금(offline·network 0·DB 0·결정론).

fake fixture 가 fetch→cluster→candidate 단계를 거치며 source_role_distribution + failures_by_stage 를
결정론으로 분류함을 잠근다. DB 단계는 offline 에서 None(정직), live-DB 어댑터는 safe-target gate·순수 매핑만 검증.
ADR#55: live_network 실 fetch 는 MockTransport(network 0·결정론)로 parser/allowlist/단계별 실패를 잠근다.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.app.services.event_ingest_pipeline import EventIngestSummary
from backend.app.tools.db_target import UnsafeWriteTargetError
from backend.app.tools.real_source_identity_smoke import (
    DEFAULT_MAX_PER_SOURCE,
    DEFAULT_MAX_RECORDS,
    build_fake_source_records,
    build_replay_batches,
    fetch_real_source_records,
    run_db_identity_smoke,
    run_offline_identity_smoke,
    summarize_db_ingest,
)
from ingestion.orchestration.cross_source_dedup import (
    cluster_records,
    semantic_identity_fingerprint,
)

# federal_register payload fixture(network 0·MockTransport 주입용). dup 1개 포함.
_FR_PAYLOAD = json.dumps({"results": [
    {"title": "Rule A on import tariffs", "publication_date": "2026-06-20", "document_number": "2026-0001"},
    {"title": "Notice B on safety standards", "publication_date": "2026-06-21", "document_number": "2026-0002"},
    {"title": "Rule A on import tariffs", "publication_date": "2026-06-20", "document_number": "2026-0001"},
]})


def test_offline_fake_fixture_deterministic_report():
    r = run_offline_identity_smoke()
    assert r["mode"] == "offline_fake" and r["real_fetch"] is False
    assert r["source_count"] == 8 and r["fetched_records"] == 8
    assert r["clusters"] == 3 and r["singletons_dropped"] == 2
    assert r["semantic_fingerprint_candidates"] == 2
    assert r["publishable_anchor_clusters"] == 2


def test_offline_source_role_distribution():
    r = run_offline_identity_smoke()
    assert r["source_role_distribution"] == {"article": 5, "official": 1, "community": 2}


def test_offline_failures_by_stage_classified():
    f = run_offline_identity_smoke()["failures_by_stage"]
    assert f["body_missing"] == 1            # missing body record
    assert f["no_cluster_singleton"] == 2    # 2 singletons
    assert f["non_publishable_role"] == 1    # community-only cluster (anchor 금지)
    assert f["no_semantic_fingerprint"] == 0


def test_offline_db_stages_none_and_no_auto_merge():
    r = run_offline_identity_smoke()
    for k in ("created_events", "held_events", "withheld_events",
              "identity_links", "adjudications", "packet_eligible", "packet_selected"):
        assert r[k] is None                  # offline 미도달(정직)
    assert r["no_auto_merge"] is True


def test_offline_bounded_truncates():
    many = build_fake_source_records() * 10   # 80 records
    r = run_offline_identity_smoke(many, max_records=10)
    assert r["fetched_records"] == 10
    assert r["records_truncated"] is True


def test_offline_default_max_records_constant():
    assert DEFAULT_MAX_RECORDS == 50


def test_offline_probe_injection_marks_real_fetch():
    recs = build_fake_source_records()
    r = run_offline_identity_smoke(probe=lambda: recs)
    assert r["mode"] == "offline_probe" and r["real_fetch"] is True
    assert r["fetched_records"] == 8


def test_community_only_cluster_has_no_publishable_anchor():
    # community 두 record 만 → 클러스터는 형성되나 identity anchor 0·non_publishable_role.
    from backend.app.tools.real_source_identity_smoke import _rec
    recs = [
        _rec(record_type="community_signal", source_id="hacker_news", canonical_url="https://hn.test/a",
             title_or_label="Shared rumor about outage spreading fast online", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="community_signal", source_id="dcinside", canonical_url="https://dc.test/b",
             title_or_label="Shared rumor about outage spreading fast online", published_at_or_observed_at="2025-06-02"),
    ]
    r = run_offline_identity_smoke(recs)
    assert r["clusters"] == 1
    assert r["publishable_anchor_clusters"] == 0
    assert r["failures_by_stage"]["non_publishable_role"] == 1
    assert r["semantic_fingerprint_candidates"] == 0


def test_summarize_db_ingest_maps_summary_fields():
    s = EventIngestSummary(enabled=True)
    s.created = 2
    s.appended = 1
    s.held = 3
    s.withheld_source_type = 1
    s.held_member_links = 4
    s.adjudications = 5
    s.singletons_dropped = 6
    db = summarize_db_ingest(s, packet_eligible=7, packet_selected=0)
    assert db["created_events"] == 2 and db["held_events"] == 3
    assert db["withheld_events"] == 1 and db["adjudications"] == 5
    assert db["held_member_links"] == 4 and db["singletons_dropped"] == 6
    assert db["packet_eligible"] == 7 and db["packet_selected"] == 0
    assert db["no_auto_merge"] is True


def test_db_smoke_blocks_unsafe_target_before_session():
    # production-like target·allow_non_dev 없음 → assert_safe_write_target 가 session 사용 전 차단.
    with pytest.raises(UnsafeWriteTargetError):
        asyncio.run(run_db_identity_smoke(
            None, app_env="production",
            database_url="postgresql+asyncpg://u:p@h:5432/event_intel_prod"))


def test_offline_record_quality_fields_present():
    r = run_offline_identity_smoke()
    assert r["records_with_body"] == 7      # 8 중 1개 missing
    assert r["records_with_canonical_url"] == 8
    assert r["records_with_published_at"] == 8
    assert "bbc" in r["source_ids"] and r["source_ids"] == sorted(r["source_ids"])


# ── ADR#55 live_network 실 fetch(MockTransport·network 0) ──────────────────────────────
def test_fetch_real_records_parses_payload_with_canonical_published():
    recs, failures = fetch_real_source_records(
        ["federal_register"], transport=lambda url: _FR_PAYLOAD)
    assert failures == {} and len(recs) == 3
    r0 = recs[0]
    assert r0["record_type"] == "official_record" and r0["source_id"] == "federal_register"
    assert r0["canonical_url"] == "https://www.federalregister.gov/d/2026-0001"
    assert r0["published_at_or_observed_at"] == "2026-06-20"
    assert r0["title_or_label"] == "Rule A on import tariffs"
    # 본문 미저장 — body_state_or_signal 만(raw_payload/body 키 부재).
    assert "raw_payload" not in r0 and "body" not in r0


def test_fetch_real_records_bounded_per_source():
    big = json.dumps({"results": [
        {"title": f"Doc {i}", "publication_date": "2026-06-20", "document_number": f"d{i}"}
        for i in range(20)]})
    recs, _ = fetch_real_source_records(
        ["federal_register"], transport=lambda url: big, max_per_source=3)
    assert len(recs) == 3                    # bounded


def test_fetch_real_records_allowlist_blocks_non_official():
    # community/market/news-HTML 등 allowlist 밖 → source_disabled(network 미접근).
    recs, failures = fetch_real_source_records(
        ["hacker_news", "coinbase_market"], transport=lambda url: _FR_PAYLOAD)
    assert recs == []
    assert failures == {"hacker_news": "source_disabled", "coinbase_market": "source_disabled"}


def test_fetch_real_records_network_error_classified():
    recs, failures = fetch_real_source_records(
        ["federal_register"], transport=lambda url: None)     # fetch None = network 실패
    assert recs == [] and failures == {"federal_register": "network_error"}


def test_fetch_real_records_parser_error_classified():
    recs, failures = fetch_real_source_records(
        ["federal_register"], transport=lambda url: "<<not json>>")
    assert recs == [] and failures == {"federal_register": "parser_error"}


def test_fetch_real_records_no_records_classified():
    recs, failures = fetch_real_source_records(
        ["federal_register"], transport=lambda url: json.dumps({"results": []}))
    assert recs == [] and failures == {"federal_register": "no_records"}


def test_fetch_real_records_missing_document_number_yields_no_canonical():
    # document_number 결측 official record → canonical None(실패 아님·official 이나 anchor 불가 = guard_only).
    payload = json.dumps({"results": [
        {"title": "Rule with no doc number", "publication_date": "2026-06-20"}]})
    recs, failures = fetch_real_source_records(
        ["federal_register"], transport=lambda url: payload)
    assert failures == {} and len(recs) == 1
    assert recs[0]["canonical_url"] is None and recs[0]["record_type"] == "official_record"


def test_fetch_real_records_missing_title_skipped():
    # title 결측 item 은 skip(헤드라인 없으면 record 아님).
    payload = json.dumps({"results": [
        {"publication_date": "2026-06-20", "document_number": "d1"},
        {"title": "Has title", "publication_date": "2026-06-21", "document_number": "d2"}]})
    recs, _ = fetch_real_source_records(["federal_register"], transport=lambda url: payload)
    assert len(recs) == 1 and recs[0]["title_or_label"] == "Has title"


def test_fetch_real_records_default_max_per_source_constant():
    assert DEFAULT_MAX_PER_SOURCE == 5


def test_live_network_probe_runs_through_offline_smoke():
    # 실 fetch(주입)→offline smoke: official 3 record → role_distribution official, body/canonical/published 충족.
    recs, _ = fetch_real_source_records(["federal_register"], transport=lambda url: _FR_PAYLOAD)
    r = run_offline_identity_smoke(probe=lambda: recs)
    assert r["real_fetch"] is True and r["source_count"] == 1
    assert r["source_role_distribution"] == {"official": 3}
    assert r["records_with_canonical_url"] == 3 and r["records_with_published_at"] == 3
    assert r["no_auto_merge"] is True


# ── ADR#56 time-series replay 배치 빌더(network 0·DB 0·결정론) ──────────────────────────
def test_build_replay_batches_shape_and_no_raw_body():
    batches = build_replay_batches()
    assert len(batches) == 2 and all(len(b) == 2 for b in batches)
    for b in batches:
        for r in b:
            # 본문 미저장 — headline/canonical/published 만(raw_payload/body 키 부재·옵션 B/C 계약).
            assert "raw_payload" not in r and "body" not in r
            assert r["record_type"] == "article_candidate"     # publishable(anchor 자격)


def test_replay_batches_cross_batch_same_event_different_url():
    # 핵심 계약: 배치 A·B 는 **같은 제목·같은 날짜**(같은 fingerprint)이나 **다른 canonical_url**(공유 anchor 없음).
    a, b = build_replay_batches()
    assert a[0]["canonical_url"] != b[0]["canonical_url"]       # 다른 URL → strong anchor 매칭 안 됨
    assert a[0]["title_or_label"] == b[0]["title_or_label"]
    fp_a = semantic_identity_fingerprint(a[0]["title_or_label"], a[0]["published_at_or_observed_at"])
    fp_b = semantic_identity_fingerprint(b[0]["title_or_label"], b[0]["published_at_or_observed_at"])
    assert fp_a is not None and fp_a == fp_b                    # 같은 fingerprint → cross-batch 후보 가능


def test_replay_each_batch_forms_strong_cluster():
    # 각 배치는 같은 canonical_url 2 record → strong duplicate cluster(CREATE 1·held 없음).
    for batch in build_replay_batches():
        clusters = cluster_records(batch)
        assert len(clusters) == 1 and clusters[0].confidence == "duplicate"
