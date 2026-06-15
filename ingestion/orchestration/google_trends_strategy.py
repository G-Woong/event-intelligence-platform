"""Phase G2-9 google_trends_explore — 정직한 hard blocker 문서화(추측 disable 아님).

조사로 확인된 사실(증거):
- trends.google.com/robots.txt는 directive 0개 → robots는 blocker가 아님.
- 그러나 Google Trends explore는 **공식 public API가 없다**(pytrends는 비공식이며 미설치).
- explore 엔드포인트는 내부 widget/token 핸드셰이크 의존 → 자동 접근 시 Google **anti-abuse 429**.
  우회(proxy/anti-bot/로그인) 금지(정책) → 정책 준수 자동 수집 경로 없음.
- trending 데이터는 별도 source ``google_trending_now``가 compliant하게 커버 중이다.

따라서 사용자 결정(2026-06-15)대로 explore는 REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT로
정직하게 닫는다 — "needs_api_integration"이라는 모호한 표현을 **검증된 증거**로 격상한다.

stdlib만. 신규 설치 0. 네트워크 0(결정적 분류, 증거는 사전 probe로 확보).
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Optional

REQUIRES_CONTRACT = "REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT"


@dataclass(frozen=True)
class GoogleTrendsAssessment:
    source_id: str
    robots_blocker: bool
    official_api_available: bool
    pytrends_installed: bool
    anti_abuse_429_observed: bool
    trending_covered_by: Optional[str]
    final_status: str
    hard_blocker_evidence: str


def _pytrends_installed() -> bool:
    try:
        return importlib.util.find_spec("pytrends") is not None
    except Exception:
        return False


def assess_google_trends(
    *,
    pytrends_installed: Optional[bool] = None,
    anti_abuse_429_observed: bool = True,
) -> GoogleTrendsAssessment:
    """google_trends_explore의 compliant 수집 가능성을 평가 → 문서화된 blocker.

    pytrends_installed 미지정 시 실제 설치 여부를 확인(주입 가능, 테스트 결정적).
    """
    has_pytrends = _pytrends_installed() if pytrends_installed is None else pytrends_installed
    evidence = (
        "no official Google Trends API; "
        f"pytrends_installed={has_pytrends} (unofficial, not present); "
        f"explore endpoint anti-abuse 429={anti_abuse_429_observed} (no-bypass: proxy/anti-bot/login forbidden); "
        "trending data already covered compliantly by source 'google_trending_now'"
    )
    return GoogleTrendsAssessment(
        source_id="google_trends_explore",
        robots_blocker=False,                 # robots는 비어있음(차단 아님)
        official_api_available=False,
        pytrends_installed=has_pytrends,
        anti_abuse_429_observed=anti_abuse_429_observed,
        trending_covered_by="google_trending_now",
        final_status=REQUIRES_CONTRACT,
        hard_blocker_evidence=evidence,
    )
