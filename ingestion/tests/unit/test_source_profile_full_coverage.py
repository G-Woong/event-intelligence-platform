"""Phase C-2 full coverage audit: canonical 소스 전수가 오케스트레이션에 연결되는지 검증.

canonical 출처: docs/ingestion/INGESTION_FINAL.md (CORE_READY 44 + READY_WITH_CAUTION 6).
네트워크 호출 없음 — fake probe/queue 주입 dry-run.
"""
from __future__ import annotations

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.orchestration.cycle_planner import select_due_sources
from ingestion.orchestration.source_profile import (
    LIVE_ELIGIBLE_VALUES,
    PROFILE_STATUS_VALUES,
    load_source_profiles,
    profiles_to_schedules,
)
from ingestion.orchestration.strategy_router import decide_strategy

# ── canonical set (INGESTION_FINAL.md 정본) ──────────────────────────────────
CORE_READY_44 = [
    # news (10)
    "bbc", "ap_news", "techcrunch", "the_verge", "zdnet_korea", "etnews",
    "yna", "hankyung", "maekyung", "aljazeera",
    # community (3)
    "hacker_news", "youtube", "product_hunt",
    # search (6)
    "naver_news_search", "naver_blog_search", "serper", "tavily", "exa", "gnews",
    # official (7)
    "gdelt", "sec_edgar", "federal_register", "opendart", "bok_ecos", "eia",
    "eu_press_corner",
    # trend (3)
    "signal_bz", "google_trending_now", "loword",
    # market (6)
    "finnhub", "twelve_data", "alpha_vantage", "polygon", "coinbase_market",
    "binance_market",
    # domain (9)
    "kofic", "igdb", "tmdb", "kopis", "aladin", "kma", "tour", "its", "culture_info",
]
CAUTION_6 = ["cnbc", "guardian", "nyt", "newsapi", "dcinside", "google_trends_explore"]
EXCLUDED_DEFERRED = ["x", "blind", "reuters", "fmkorea", "google_programmable_search",
                     "krx_kind", "reddit"]


def _profiles():
    return load_source_profiles()


def _by_id():
    return {p.source_id: p for p in _profiles()}


# ── C2-3 coverage ────────────────────────────────────────────────────────────

def test_core_ready_count_is_44():
    assert len(CORE_READY_44) == 44


def test_all_canonical_sources_present():
    by_id = _by_id()
    missing = [s for s in (CORE_READY_44 + CAUTION_6) if s not in by_id]
    assert missing == [], f"missing from source_profiles.yaml: {missing}"


def test_excluded_deferred_registered_but_disabled():
    by_id = _by_id()
    for s in EXCLUDED_DEFERRED:
        assert s in by_id, f"{s} not registered"
        assert by_id[s].enabled is False
        assert by_id[s].live_eligible == "false"
        assert by_id[s].skip_reason is not None


def test_no_duplicate_source_ids():
    profiles = _profiles()
    ids = [p.source_id for p in profiles]
    assert len(ids) == len(set(ids))


def test_enabled_profiles_have_positive_interval_and_purpose():
    for p in _profiles():
        if p.enabled:
            assert p.min_interval_seconds > 0, p.source_id
            assert p.purpose, p.source_id


def test_community_sources_unconfirmed_policy():
    for p in _profiles():
        if p.is_community:
            assert p.confirmation_policy == "unconfirmed_until_corroborated", p.source_id


def test_requires_api_key_enabled_sources_are_not_live_eligible():
    for p in _profiles():
        if p.enabled and p.requires_api_key:
            assert p.live_eligible in ("false", "conservative"), p.source_id
            assert p.skip_reason is not None or p.live_eligible == "conservative"


def test_disabled_sources_not_live_eligible():
    for p in _profiles():
        if not p.enabled:
            assert p.live_eligible == "false", p.source_id


def test_profile_status_and_live_eligible_enums_valid():
    for p in _profiles():
        assert p.profile_status in PROFILE_STATUS_VALUES, p.source_id
        assert p.live_eligible in LIVE_ELIGIBLE_VALUES, p.source_id


def test_all_profiles_convert_to_schedules():
    profiles = _profiles()
    schedules = profiles_to_schedules(profiles)
    assert len(schedules) == len(profiles)


def test_select_due_runs_over_all_without_error():
    from datetime import datetime, timezone

    schedules = profiles_to_schedules(_profiles())
    due = select_due_sources(schedules, datetime.now(timezone.utc))
    # disabled 소스는 due에서 빠진다
    by_id = _by_id()
    for sid in due:
        assert by_id[sid].enabled is True


def test_disabled_excluded_from_due():
    schedules = profiles_to_schedules(_profiles())
    from datetime import datetime, timezone

    due = set(select_due_sources(schedules, datetime.now(timezone.utc)))
    for s in EXCLUDED_DEFERRED:
        assert s not in due


def test_strategy_decision_for_every_source():
    for p in _profiles():
        d = decide_strategy(p)
        assert d.source_id == p.source_id
        if p.is_community:
            assert d.confirmation_policy == "unconfirmed_until_corroborated"


# ── C2-4 full dry-run orchestration ──────────────────────────────────────────

class FakeQueue:
    def __init__(self):
        self.items = []

    def enqueue(self, item):
        item_id = f"id-{len(self.items)}"
        self.items.append({"_id": item_id, **item})
        return item_id


def _fake_success(sid, **kw):
    return CollectionProbeResult(
        source_id=sid, status="LIVE_SUCCESS", items_found=3,
        artifact_paths=ArtifactPaths(raw_payload=f"/raw/{sid}"),
    )


def test_dry_run_all_enabled_sources_processed():
    """전체 enabled+due 소스가 fake probe에 정확히 1회씩 전달되고 enqueue된다."""
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    profiles = [p for p in _profiles() if p.enabled]
    seen = []

    def probe(sid, **kw):
        seen.append(sid)
        return _fake_success(sid)

    q = FakeQueue()
    # state_path 없음 → 전부 due(최초). schedules 대신 profiles 경로.
    report = run_cycle(profiles=profiles, queue=q, probe_fn=probe)

    assert sorted(seen) == sorted(p.source_id for p in profiles)
    assert len(seen) == len(set(seen))  # 정확히 1회씩
    assert report.sources_succeeded == len(profiles)
    assert report.items_enqueued == len(profiles)


def test_dry_run_disabled_not_probed():
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    profiles = _profiles()  # enabled + disabled 모두
    seen = []

    def probe(sid, **kw):
        seen.append(sid)
        return _fake_success(sid)

    run_cycle(profiles=profiles, queue=FakeQueue(), probe_fn=probe)
    for s in EXCLUDED_DEFERRED:
        assert s not in seen


def test_dry_run_isolates_single_failure():
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    profiles = [p for p in _profiles() if p.enabled][:5]

    def probe(sid, **kw):
        if sid == profiles[0].source_id:
            raise RuntimeError("boom")
        return _fake_success(sid)

    report = run_cycle(profiles=profiles, queue=FakeQueue(), probe_fn=probe)
    assert report.sources_failed >= 1
    assert report.sources_succeeded == len(profiles) - 1


def test_live_only_skips_non_eligible_with_reason():
    """live_only=True면 live_eligible!=true 소스는 SKIPPED(skip_reason)로 기록된다."""
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    profiles = _profiles()
    probed = []

    def probe(sid, **kw):
        probed.append(sid)
        return _fake_success(sid)

    report = run_cycle(profiles=profiles, queue=FakeQueue(), probe_fn=probe, live_only=True)

    by_id = _by_id()
    # 실제 호출된 건 전부 live_eligible=true
    for sid in probed:
        assert by_id[sid].live_eligible == "true"
    # skip된 소스는 skip_reason 보유
    skipped = [o for o in report.outcomes if o.status == "SKIPPED"]
    assert len(skipped) > 0
    assert all(o.skip_reason for o in skipped)
    assert report.sources_skipped == len(skipped)


def test_live_only_community_keeps_unconfirmed_in_decision():
    """community가 live 가능해도 confirmation policy는 unconfirmed로 유지된다."""
    by_id = _by_id()
    hn = by_id["hacker_news"]
    assert hn.live_eligible == "true"
    assert decide_strategy(hn).confirmation_policy == "unconfirmed_until_corroborated"
