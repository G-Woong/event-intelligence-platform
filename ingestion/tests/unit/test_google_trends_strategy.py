"""G2-9: google_trends_explore — robots 차단 아님 + 공식 API 없음 + anti-abuse 429 → 문서화된 blocker.

추측 disable가 아니라 검증된 evidence 기반 REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT.
"""
from __future__ import annotations

from ingestion.orchestration.google_trends_strategy import (
    REQUIRES_CONTRACT,
    assess_google_trends,
)


def test_assessment_is_documented_blocker_not_assumption():
    a = assess_google_trends(pytrends_installed=False, anti_abuse_429_observed=True)
    assert a.final_status == REQUIRES_CONTRACT
    assert a.robots_blocker is False                 # robots는 차단 아님(정직)
    assert a.official_api_available is False
    assert a.trending_covered_by == "google_trending_now"
    # evidence에 핵심 근거가 모두 들어가야 함(사람이 납득 가능)
    ev = a.hard_blocker_evidence.lower()
    assert "no official" in ev and "pytrends" in ev and "anti-abuse 429" in ev


def test_pytrends_detection_runs_without_injection():
    # 실제 환경에서 pytrends는 미설치(조사 확인). 주입 없이도 동작.
    a = assess_google_trends()
    assert a.pytrends_installed is False
    assert a.final_status == REQUIRES_CONTRACT
