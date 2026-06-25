"""ADR#54 — real-source identity smoke 진단 잠금(offline·network 0·DB 0·결정론).

fake fixture 가 fetch→cluster→candidate 단계를 거치며 source_role_distribution + failures_by_stage 를
결정론으로 분류함을 잠근다. DB 단계는 offline 에서 None(정직), live-DB 어댑터는 safe-target gate·순수 매핑만 검증.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.app.services.event_ingest_pipeline import EventIngestSummary
from backend.app.tools.db_target import UnsafeWriteTargetError
from backend.app.tools.real_source_identity_smoke import (
    DEFAULT_MAX_RECORDS,
    build_fake_source_records,
    run_db_identity_smoke,
    run_offline_identity_smoke,
    summarize_db_ingest,
)


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
