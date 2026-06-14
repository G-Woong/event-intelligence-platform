"""뉴스/HTML 본문 fetch strategy ladder (Phase E-3, 설계 04/08/09).

NEEDS_BODY_FETCH(뉴스)와 HTML_UNSUPPORTED(zdnet/etnews)를 끝까지 추적하기 위한 ladder:
  httpx GET → trafilatura → readability → bs4/static → (policy-safe) browser render → body_state.

핵심 원칙(no bypass):
  - paywall/login/captcha **마커가 감지되면 우회하지 않는다** — 브라우저 렌더도 시도하지 않고
    그대로 *_BLOCKED_NO_BYPASS로 닫을 근거로 보고한다.
  - robots disallow면 fetch 자체를 하지 않는다.
  - 길이만으로 present 판정하지 않는다(body_state cascade가 snippet_only를 강등).
  - 브라우저(selenium/playwright)는 source별 최대 1회. 미설치/실패는 TOOL_UNAVAILABLE.
  - 네트워크 호출은 주입형 fn으로 격리(단위 테스트 network 0). stdlib + 기존 자산만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ingestion.orchestration.body_state import (
    FULL_BODY_MIN,
    PARTIAL_MIN,
    _EXCERPT_MARKERS,
    assess_body_state,
)

# 본문이 잘렸음을 시사하는 **구체** 차단 문구만 사용한다(footer의 일반 'subscribe'/'구독'/
# 'login'/script의 'recaptcha' 같은 단어는 false-positive를 양산하므로 제외 — 리뷰 흡수).
_PAYWALL_MARKERS = (
    "subscribe to continue", "subscription required", "to continue reading",
    "already a subscriber", "subscriber-only", "subscriber only",
    "create a free account to", "sign up to read", "register to continue",
    "this article is for subscribers", "this content is for subscribers",
    "구독자 전용", "유료회원 전용", "유료 회원 전용", "로그인 후 이용",
)
_LOGIN_MARKERS = (
    "sign in to continue", "log in to continue", "log in to read",
    "you must be logged in", "members only content", "회원 전용", "로그인이 필요",
)
_CAPTCHA_MARKERS = (
    "verify you are human", "unusual traffic from your", "are you a robot",
    "please complete the security check", "enable javascript and cookies to continue",
)

# present이지만 이 길이 미만이고 title과도 무관하면 teaser/프로모션으로 보고 full로 인정하지 않는다
# (cnbc Pro 프로모션 492자가 기사 본문으로 둔갑한 사례 차단 — 리뷰 흡수).
CONFIDENT_FULL_MIN = 600

_BOILERPLATE_MARKERS = (
    "subscribe", "sign in", "log in", "create an account", "cookie",
    "accept all", "newsletter", "advertisement",
)

# fetch_fn(url) -> (http_status|None, html|None, error_type|None)
FetchFn = Callable[[str], "tuple[Optional[int], Optional[str], Optional[str]]"]
# extract_fn(html, url) -> (body_text|None, extractor_name)
ExtractFn = Callable[[str, str], "tuple[Optional[str], str]"]
# robots_fn(url) -> bool
RobotsFn = Callable[[str], bool]
# browser_fn(url) -> (html|None, status_str)  ("ok"|"NOT_READY"|"JS_RENDER_FAIL")
BrowserFn = Callable[[str], "tuple[Optional[str], str]"]


@dataclass(frozen=True)
class LadderBodyResult:
    source_id: str
    url: Optional[str]
    attempted: bool
    status: str  # SUCCESS|PARTIAL|EXCERPT_ONLY|NO_BODY|PAYWALL|LOGIN|CAPTCHA|ROBOTS_BLOCKED|
                 # HTTP_ERROR|FETCH_ERROR|SKIPPED_NO_URL|TOOL_UNAVAILABLE
    http_status: Optional[int]
    body_text: Optional[str]  # internal_only — 직렬화 시 길이/상태만 노출
    body_length: int
    body_state: str
    extractor_used: Optional[str]
    boilerplate_risk: Optional[str]
    excerpt_marker_detected: bool
    paywall_marker: bool
    login_marker: bool
    captcha_marker: bool
    browser_used: bool
    browser_available: bool
    tool_unavailable: bool
    error_type: Optional[str]
    strategies_tried: tuple[str, ...] = field(default_factory=tuple)


def _scan_markers(html: str) -> tuple[bool, bool, bool]:
    low = html.lower()
    paywall = any(m in low for m in _PAYWALL_MARKERS)
    login = any(m in low for m in _LOGIN_MARKERS)
    captcha = any(m in low for m in _CAPTCHA_MARKERS)
    return paywall, login, captcha


def _detect_boilerplate(body: str) -> str:
    low = body.lower()
    hits = sum(1 for m in _BOILERPLATE_MARKERS if m in low)
    return "high" if hits >= 3 else ("medium" if hits >= 1 else "low")


# overlap 판정에서 제외할 흔한 불용어(이 단어가 우연히 겹쳐 프로모션 본문을 통과시키는 것 방지).
_STOPWORDS = frozenset({
    "from", "than", "ever", "that", "this", "with", "have", "will", "your", "about",
    "what", "when", "then", "them", "they", "were", "been", "into", "over", "more",
    "most", "some", "such", "only", "also", "very", "just", "like", "here", "there",
    "their", "would", "could", "should", "after", "before", "while", "where", "which",
    "news", "report", "says", "said", "year", "today", "보도", "관련", "이번", "그리고",
})


def _title_overlap(body: str, title: Optional[str]) -> bool:
    """추출 본문이 기사 title의 **유의미 content 토큰**(len>=4, 불용어 제외)을 포함하는가.

    title과 전혀 무관한 본문(프로모션/구독 위젯을 잘못 추출한 경우)을 걸러낸다.
    title이 없으면 판정 불가로 보고 False(길이 기준에 위임).
    """
    if not title or not body:
        return False
    low = body.lower()
    toks = [t for t in re_split_tokens(title.lower())
            if len(t) >= 4 and t not in _STOPWORDS]
    return any(t in low for t in toks)


def re_split_tokens(s: str) -> list[str]:
    import re
    return [t for t in re.split(r"[^0-9a-z가-힣]+", s) if t]


def _bs4_static_extract(html: str, url: str) -> "tuple[Optional[str], str]":
    """trafilatura/readability 실패 시 bs4 정적 추출: <article> 또는 <p> 본문, script/style 제거."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return None, "none"
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return None, "none"
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    article = soup.find("article")
    if article is not None:
        text = article.get_text(" ", strip=True)
        if text and len(text) >= PARTIAL_MIN:
            return text, "bs4_article"
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text = " ".join(x for x in paras if x)
    if text and len(text) >= PARTIAL_MIN:
        return text, "bs4_paragraphs"
    return None, "none"


def _trafilatura_readability(html: str, url: str) -> "tuple[Optional[str], str]":
    try:
        from ingestion.tools.trafilatura_extractor import extract_with_trafilatura
        res = extract_with_trafilatura(html, url)
        if res.success and res.body and len(res.body.strip()) >= PARTIAL_MIN:
            return res.body, "trafilatura"
    except Exception:
        pass
    try:
        from ingestion.tools.readability_extractor import extract_with_readability
        res = extract_with_readability(html, url)
        if res.success and res.body and len(res.body.strip()) >= PARTIAL_MIN:
            return res.body, "readability"
    except Exception:
        pass
    return None, "none"


def _default_fetch_fn(url: str) -> "tuple[Optional[int], Optional[str], Optional[str]]":
    from ingestion.tools.html_fetch_tool import fetch_html
    r = fetch_html(url, strategy="httpx_direct", timeout=15.0)
    if not r.success:
        return r.status_code or None, None, r.error_message or "fetch_failed"
    return r.status_code or None, r.html or None, None


def _default_robots(url: str) -> bool:
    from ingestion.orchestration.full_source_revival import _default_robots_allows
    return _default_robots_allows(url)


def _default_browser_fn(url: str) -> "tuple[Optional[str], str]":
    from ingestion.fetch_strategies.selenium_strategy import SeleniumRenderStrategy
    res = SeleniumRenderStrategy(headless=True, timeout_sec=20).fetch(url)
    return res.html, res.status


def fetch_body_with_ladder(
    url: Optional[str],
    *,
    source_id: str,
    title: Optional[str] = None,
    html: Optional[str] = None,
    fetch_fn: Optional[FetchFn] = None,
    extract_fn: Optional[ExtractFn] = None,
    bs4_fn: Optional[ExtractFn] = None,
    robots_fn: Optional[RobotsFn] = None,
    allow_browser: bool = False,
    browser_fn: Optional[BrowserFn] = None,
    browser_available: bool = True,
    full_threshold: int = FULL_BODY_MIN,
) -> LadderBodyResult:
    """본문 fetch ladder를 1회 실행. paywall/login/captcha 마커 시 우회 없이 그대로 보고.

    ``html``을 직접 주면(zdnet/etnews의 저장된 raw_html 등) httpx fetch를 건너뛰고 추출만 수행한다.
    """
    tried: list[str] = []
    extract = extract_fn or _trafilatura_readability
    bs4 = bs4_fn or _bs4_static_extract

    http_status: Optional[int] = None
    if html is None:
        if not url:
            return _empty(source_id, None, "SKIPPED_NO_URL", "no_url", tried, browser_available)
        robots = robots_fn or _default_robots
        tried.append("robots_check")
        if not robots(url):
            return _empty(source_id, url, "ROBOTS_BLOCKED", "robots_disallow", tried, browser_available)
        fetch = fetch_fn or _default_fetch_fn
        tried.append("httpx_fetch")
        try:
            http_status, html, ferr = fetch(url)
        except Exception as exc:
            return _empty(source_id, url, "FETCH_ERROR", type(exc).__name__, tried, browser_available)
        if ferr or not html:
            status = "HTTP_ERROR" if (http_status and http_status >= 400) else "FETCH_ERROR"
            return _empty(source_id, url, status, ferr or "no_html", tried, browser_available,
                          http_status=http_status)
    else:
        tried.append("stored_html")

    paywall, login, captcha = _scan_markers(html)
    # 정적 추출(trafilatura → readability → bs4)
    tried.append("trafilatura_readability")
    body, extractor = extract(html, url)
    if not body:
        tried.append("bs4_static")
        body, extractor = bs4(html, url)

    browser_used = False
    tool_unavailable = False
    # 정적 추출이 불충분하고, **차단 마커가 없을 때만** policy-safe 브라우저 렌더 1회.
    insufficient = (not body) or (assess_body_state(
        body_text=body, full_threshold=full_threshold).extraction_status == "snippet_only")
    if insufficient and allow_browser and not (paywall or login or captcha):
        tried.append("browser_render")
        bfn = browser_fn or _default_browser_fn
        try:
            b_html, b_status = bfn(url)
        except Exception:
            b_html, b_status = None, "JS_RENDER_FAIL"
        if b_status == "ok" and b_html:
            browser_used = True
            p2, l2, c2 = _scan_markers(b_html)
            paywall, login, captcha = paywall or p2, login or l2, captcha or c2
            b_body, b_extractor = extract(b_html, url)
            if not b_body:
                b_body, b_extractor = bs4(b_html, url)
            if b_body and (not body or len(b_body) > len(body or "")):
                body, extractor = b_body, f"browser+{b_extractor}"
        else:
            tool_unavailable = True
    elif insufficient and allow_browser and (paywall or login or captcha):
        tried.append("browser_skipped_marker_no_bypass")

    body = (body or "").strip()
    blen = len(body)
    excerpt = bool(body) and any(m in body[-200:].lower() for m in _EXCERPT_MARKERS)
    boiler = _detect_boilerplate(body) if body else None
    state = assess_body_state(body_text=body, full_threshold=full_threshold)
    # 확신 가능한 full body = present + (길이 충분 OR title과 토큰 겹침). 차단 마커가 있어도
    # 본문을 실제로 확보했으면(우회가 아니라 서빙된 HTML에서 추출) SUCCESS로 인정한다. 반대로
    # present이지만 짧고 title과 무관하면(프로모션/teaser) full로 둔갑시키지 않는다(긍정편향 차단).
    confident_full = state.extraction_status == "present" and (
        blen >= CONFIDENT_FULL_MIN or _title_overlap(body, title))
    if confident_full:
        status = "SUCCESS"
    elif state.extraction_status == "partial" and (paywall or login or captcha) is False:
        status = "PARTIAL"
    elif captcha:
        status = "CAPTCHA"
    elif login:
        status = "LOGIN"
    elif paywall:
        status = "PAYWALL"
    elif state.extraction_status == "present":
        # present이나 짧고 title 무관 + 차단마커 없음 → teaser로 보고 발췌 처리
        status = "EXCERPT_ONLY"
    elif state.extraction_status == "partial":
        status = "PARTIAL"
    elif state.extraction_status == "snippet_only":
        status = "EXCERPT_ONLY"
    else:
        status = "NO_BODY"
    return LadderBodyResult(
        source_id=source_id, url=url, attempted=True, status=status,
        http_status=http_status, body_text=(body or None), body_length=blen,
        body_state=state.extraction_status, extractor_used=(extractor if body else None),
        boilerplate_risk=boiler, excerpt_marker_detected=excerpt,
        paywall_marker=paywall, login_marker=login, captcha_marker=captcha,
        browser_used=browser_used, browser_available=browser_available,
        tool_unavailable=tool_unavailable, error_type=None,
        strategies_tried=tuple(tried),
    )


def _empty(source_id, url, status, error_type, tried, browser_available,
           http_status=None) -> LadderBodyResult:
    return LadderBodyResult(
        source_id=source_id, url=url, attempted=(status not in ("SKIPPED_NO_URL", "ROBOTS_BLOCKED")),
        status=status, http_status=http_status, body_text=None, body_length=0,
        body_state="missing", extractor_used=None, boilerplate_risk=None,
        excerpt_marker_detected=False, paywall_marker=False, login_marker=False,
        captcha_marker=False, browser_used=False, browser_available=browser_available,
        tool_unavailable=False, error_type=error_type, strategies_tried=tuple(tried),
    )
