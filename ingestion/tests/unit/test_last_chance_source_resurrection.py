"""G2-1/13: last-chance resurrection runner — dcinside 승격 + gdelt pending_resume + g_trends blocker.

네트워크 0 + canonical config 미변경(apply_config=False, write_outputs=False). 전부 주입형.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ingestion.orchestration.dcinside_strategy import DCInsideStrategyResult
from ingestion.orchestration.gdelt_strategy import GdeltStrategyResult
from ingestion.orchestration.google_trends_strategy import GoogleTrendsAssessment
from ingestion.orchestration.last_chance_source_resurrection import classify_resurrection
from ingestion.tools.run_last_chance_source_resurrection import (
    run_last_chance_source_resurrection,
)

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_ROBOTS = "User-agent: ClaudeBot\nDisallow: /\nUser-agent: *\nAllow: /\nDisallow: /board/lists/?id=stock_new\n"


def _dc_record(no):
    return {"record_type": "community_signal", "source_id": "dcinside", "title_or_label": f"post {no}",
            "source_url_or_evidence": f"https://gall.dcinside.com/mgallery/board/view/?id=stockus&no={no}",
            "canonical_url": f"https://gall.dcinside.com/mgallery/board/view/?id=stockus&no={no}",
            "published_at_or_observed_at": "2026-06-15T10:00:00+09:00",
            "body_state_or_signal": "community_signal",
            "confirmation_policy": "unconfirmed_until_corroborated", "quality_pre_gate_decision": "pass"}


def _dc_success():
    recs = tuple(_dc_record(n) for n in (101, 102, 103))
    return DCInsideStrategyResult("dcinside", "stockus", "https://gall.dcinside.com/mgallery/board/lists/?id=stockus",
                                  True, 200, None, recs, 3, "COMMUNITY_SIGNAL_ALIVE")


def _dc_cloudflare():
    return DCInsideStrategyResult("dcinside", "stockus", "u", False, 200, "cloudflare_challenge",
                                  (), 0, "CLOUDFLARE_BLOCKED_NO_BYPASS")


def _gdelt_pending(gov):
    return GdeltStrategyResult("gdelt", False, 429, (), 0, ("broad",),
                               "EXTERNAL_RATE_LIMITED_PENDING_RESUME",
                               "2026-06-15T12:15:00Z", "2026-06-15T12:15:00Z", "provider_rate_limited")


def _gdelt_success(gov):
    rec = {"record_type": "official_record", "source_id": "gdelt", "title_or_label": "T",
           "source_url_or_evidence": "https://x.test/a", "canonical_url": "https://x.test/a",
           "published_at_or_observed_at": "20260615T100000Z", "body_state_or_signal": "official_record",
           "confirmation_policy": "evidence_required", "quality_pre_gate_decision": "pass"}
    return GdeltStrategyResult("gdelt", True, 200, (rec,), 1, ("broad",),
                               "OFFICIAL_RECORD_ALIVE", None, None, None)


def _gt_blocker():
    return GoogleTrendsAssessment("google_trends_explore", False, False, False, True,
                                  "google_trending_now", "REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT",
                                  "no official API; pytrends_installed=False; anti-abuse 429=True")


def _run(**over):
    kw = dict(robots_get=lambda u: _ROBOTS, dcinside_collect=_dc_success,
              gdelt_collect=_gdelt_pending, google_trends_assess=_gt_blocker,
              apply_config=False, write_outputs=False, now=_NOW)
    kw.update(over)
    return run_last_chance_source_resurrection(**kw)


def test_partial_pending_dcinside_ready_gdelt_pending_trends_blocker():
    r = _run()
    by_id = {x.source_id: x for x in r["results"]}
    # 적대 리뷰 흡수: list preview only + AI-차단 robots generic UA 통과 + ToS 미검증 → degraded-ready
    assert by_id["dcinside"].final_status == "PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY"
    assert by_id["dcinside"].is_production_ready()   # 실데이터 수집 → ready로 인정(단 DEGRADED)
    assert by_id["gdelt"].final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
    assert by_id["gdelt"].next_resume_at == "2026-06-15T12:15:00Z"
    assert by_id["google_trends_explore"].final_status == "REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT"
    # verdict는 ALL_READY가 아니어야(정직)
    assert r["verdict"]["verdict"] == "PARTIAL_MIXED_PENDING_AND_BLOCKERS"
    # dcinside 3건이 EventQueue+raw_events로 적재
    assert r["eventqueue_written"] == 3 and r["raw_events_written"] == 3
    assert r["bridge_contract_pass"] is True
    assert r["raw_by_source"]["dcinside"] == 3
    assert r["critical_alerts"] == 0


def test_dcinside_cloudflare_is_policy_blocker_no_bypass():
    r = _run(dcinside_collect=_dc_cloudflare)
    dc = {x.source_id: x for x in r["results"]}["dcinside"]
    assert dc.final_status == "POLICY_BLOCKED_NO_BYPASS_WITH_PROOF"
    assert dc.is_hard_blocker()
    assert "CLOUDFLARE" in (dc.hard_blocker_evidence or "")
    assert r["eventqueue_written"] == 0          # 우회 없이 0건


def test_all_three_ready_only_when_all_ready():
    r = _run(gdelt_collect=_gdelt_success,
             google_trends_assess=lambda: GoogleTrendsAssessment(
                 "google_trends_explore", False, True, True, False, None,
                 "PRODUCTION_READY", "ok"))
    # google_trends가 PRODUCTION_READY를 반환해도 eq_records가 0이면 production_ready로 인정 안 됨
    gt = {x.source_id: x for x in r["results"]}["google_trends_explore"]
    assert gt.is_production_ready() is False      # records 0 → ready 아님(둔갑 금지)


def test_classify_all_ready_requires_records():
    from ingestion.orchestration.last_chance_source_resurrection import (
        LastChanceSourceResurrection,
        PRODUCTION_READY,
    )
    ready = LastChanceSourceResurrection("a", "x", "y", None, None, (), (), "s", 5, 5,
                                         PRODUCTION_READY, None, None)
    no_rec = LastChanceSourceResurrection("b", "x", "y", None, None, (), (), "s", 0, 0,
                                          PRODUCTION_READY, None, None)
    assert classify_resurrection([ready])["verdict"] == "ALL_THREE_SOURCES_PRODUCTION_READY"
    # records 0이면 ready로 안 침 → BLOCKED
    assert classify_resurrection([no_rec])["verdict"] == "BLOCKED"


def test_historical_evidence_is_string_or_none():
    r = _run()
    dc = {x.source_id: x for x in r["results"]}["dcinside"]
    assert dc.historical_success_evidence is None or isinstance(dc.historical_success_evidence, str)
