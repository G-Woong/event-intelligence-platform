"""Phase G-6 News body rescue — 여러 후보 URL에 body ladder를 적용해 최선의 본문 확보.

cnbc 등은 Phase F에서 EXTERNAL_API_ERROR(EXCERPT_ONLY)로 남았다. CNBC Pro 프로모션이
기사 본문으로 둔갑하던 문제는 E-3에서 confident_full+title-overlap 게이트로 막았다. 이 모듈은
RSS item별 본문 후보를 ladder(httpx→trafilatura→readability→bs4→policy-safe browser)로 시도해
ARTICLE_BODY_ALIVE 또는 ARTICLE_PARTIAL_ALIVE를 판정한다. 우회는 하지 않는다(paywall/login/
captcha 마커 시 즉시 차단).

stdlib + 기존 body_fetch_strategy. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ingestion.orchestration.body_fetch_strategy import fetch_body_with_ladder


@dataclass(frozen=True)
class BodyRescueResult:
    source_id: str
    attempted_urls: int
    best_status: str          # SUCCESS | PARTIAL | EXCERPT_ONLY | PAYWALL | LOGIN | CAPTCHA | NO_BODY | ...
    best_url: Optional[str]
    extractor_used: Optional[str]
    body_length: int
    readiness_verdict: str    # ARTICLE_BODY_ALIVE | ARTICLE_PARTIAL_ALIVE | BLOCKED_NO_BYPASS | NO_BODY
    paywall_marker: bool
    login_marker: bool
    captcha_marker: bool


# 본문 readiness 우선순위(높을수록 좋음) — best 선택용
_STATUS_RANK = {
    "SUCCESS": 5, "PARTIAL": 4, "EXCERPT_ONLY": 3,
    "PAYWALL": 2, "LOGIN": 2, "CAPTCHA": 2,
    "NO_BODY": 1, "HTTP_ERROR": 1, "FETCH_ERROR": 1,
    "ROBOTS_BLOCKED": 1, "SKIPPED_NO_URL": 0, "TOOL_UNAVAILABLE": 1,
}


def _verdict(status: str) -> str:
    if status == "SUCCESS":
        return "ARTICLE_BODY_ALIVE"
    if status == "PARTIAL":
        return "ARTICLE_PARTIAL_ALIVE"
    if status in ("PAYWALL", "LOGIN", "CAPTCHA"):
        return f"{status}_BLOCKED_NO_BYPASS"
    return "NO_BODY"


def rescue_news_body(
    candidates,
    *,
    source_id: str,
    max_candidates: int = 3,
    allow_browser: bool = False,
    fetch_fn=None,
    extract_fn=None,
    bs4_fn=None,
    robots_fn=None,
    browser_fn=None,
    browser_available: bool = False,
) -> BodyRescueResult:
    """candidate(url+title) 목록에 ladder 적용 → 최선의 body 판정.

    candidates: (url, title) 튜플 또는 .source_url/.title 속성 객체의 시퀀스.
    confident_full/excerpt 판정은 body_fetch_strategy에 위임(프로모션 둔갑 방지 유지).
    """
    pairs = []
    for c in candidates:
        if isinstance(c, (tuple, list)) and len(c) >= 2:
            pairs.append((c[0], c[1]))
        else:
            pairs.append((getattr(c, "source_url", None) or getattr(c, "canonical_url", None),
                          getattr(c, "title", None)))
    pairs = [(u, t) for (u, t) in pairs if u][:max_candidates]

    best = None
    for url, title in pairs:
        r = fetch_body_with_ladder(
            url, source_id=source_id, title=title,
            fetch_fn=fetch_fn, extract_fn=extract_fn, bs4_fn=bs4_fn, robots_fn=robots_fn,
            allow_browser=allow_browser, browser_fn=browser_fn, browser_available=browser_available,
        )
        if best is None or _STATUS_RANK.get(r.status, 0) > _STATUS_RANK.get(best.status, 0):
            best = r
        if r.status == "SUCCESS":
            break  # 최고 등급이면 조기 종료

    if best is None:
        return BodyRescueResult(source_id, 0, "SKIPPED_NO_URL", None, None, 0,
                                "NO_BODY", False, False, False)
    return BodyRescueResult(
        source_id=source_id, attempted_urls=len(pairs), best_status=best.status,
        best_url=best.url, extractor_used=best.extractor_used, body_length=best.body_length,
        readiness_verdict=_verdict(best.status),
        paywall_marker=best.paywall_marker, login_marker=best.login_marker,
        captcha_marker=best.captcha_marker,
    )
