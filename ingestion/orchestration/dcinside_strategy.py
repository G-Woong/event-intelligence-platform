"""Phase G2-8 dcinside rescue strategy — robots 허용 갤러리만 static fetch → community_signal.

조사로 확인된 사실:
- robots(User-agent: *)는 일부 갤러리(stock_new 등 15개)만 Disallow하고 나머지는 Allow.
- robots 허용 갤러리(예: stockus)는 정직한 UA static GET에 HTTP 200 정상 HTML 응답
  (Cloudflare 챌린지/캡차/로그인 없음, server=nginx).
- 따라서 우회 없이 list 메타데이터(title/url/time/조회/댓글)를 community_signal로 수집 가능.

no-bypass 보장:
- robots disallow 갤러리는 호출하지 않는다(robots_allowed=False면 즉시 중단).
- 응답에 Cloudflare/captcha/login 마커가 보이면 파싱하지 않고 *_BLOCKED_NO_BYPASS로 중단.
- full article body가 아니라 공개 list 메타데이터만 수집(저작권/정책 보수적).

stdlib + bs4(기설치) + httpx(기설치). 신규 설치 0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from ingestion.orchestration.full_source_revival import build_eventqueue_record

# http_get(url) -> (status_code|None, text|None)
HttpGet = Callable[[str], "tuple[Optional[int], Optional[str]]"]

_UA = "Mozilla/5.0 (compatible; eventintel-collector/1.0)"
_VIEW_RE = re.compile(r"/board/view/\?id=")
_CF_MARKERS = ("just a moment", "attention required", "cf-chl", "checking your browser")
_CAPTCHA_MARKERS = ("kcaptcha", "verify you are human", "i'm not a robot")
_LOGIN_MARKERS = ("로그인이 필요", "login required", "please log in")
_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


@dataclass(frozen=True)
class DCInsideStrategyResult:
    source_id: str
    gallery_id: str
    attempted_url: str
    success: bool
    status_code: Optional[int]
    blocked_reason: Optional[str]
    records: tuple[dict, ...]
    item_count: int
    verdict: str


def _default_http_get(url: str) -> "tuple[Optional[int], Optional[str]]":
    import httpx
    r = httpx.get(url, timeout=20.0, headers={"User-Agent": _UA}, follow_redirects=True)
    return r.status_code, r.text


def _norm_kst(date_title: Optional[str], date_text: Optional[str]) -> Optional[str]:
    """gall_date[title]='YYYY-MM-DD HH:MM:SS'(KST) → ISO. 없으면 text 기반 date-only."""
    if date_title and _DT_RE.match(date_title.strip()):
        return date_title.strip().replace(" ", "T") + "+09:00"
    if date_text:
        t = date_text.strip()
        m = re.match(r"^(\d{2})\.(\d{2})\.(\d{2})$", t)   # 26.01.20 → 2026-01-20
        if m:
            return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def list_url_for(gallery_id: str, *, minor: bool = True) -> str:
    seg = "mgallery/board/lists" if minor else "board/lists"
    return f"https://gall.dcinside.com/{seg}/?id={gallery_id}"


def parse_list_rows(html: str, gallery_id: str, *, limit: int = 30) -> list[dict]:
    """dcinside list HTML → community_signal EventQueue record 목록.

    공지/광고 행(gall_num이 숫자가 아님)은 제외. view 링크 없는 행 제외.

    PII 보수: 작성자 닉네임(.gall_writer)은 **의도적으로 수집하지 않는다**(title/url/time만).
    가치 경계: 익명 갤러리 제목은 unconfirmed_until_corroborated로만 싣는다 — 펌핑성/투자권유
    콘텐츠가 event로 직행하지 않도록 하위 quality/safety gate에서 corroboration을 요구한다.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []
    for tr in soup.select("tr.ub-content"):
        num_el = tr.select_one(".gall_num")
        num = num_el.get_text(strip=True) if num_el else ""
        if not num.isdigit():           # 공지/설문/광고 행 skip
            continue
        a = tr.select_one(".gall_tit a")
        if a is None:
            continue
        href = a.get("href") or ""
        if not _VIEW_RE.search(href):
            continue
        url = href if href.startswith("http") else "https://gall.dcinside.com" + href
        title = a.get_text(strip=True)
        if not title:
            continue
        date_el = tr.select_one(".gall_date")
        observed = _norm_kst(date_el.get("title") if date_el else None,
                             date_el.get_text(strip=True) if date_el else None)
        records.append(build_eventqueue_record(
            record_type="community_signal", source_id="dcinside",
            title_or_label=title, source_url_or_evidence=url, canonical_url=url,
            published_at_or_observed_at=observed, body_state_or_signal="community_signal",
            confirmation_policy="unconfirmed_until_corroborated", quality_pre_gate_decision="pass",
        ))
        if len(records) >= limit:
            break
    return records


def _detect_block(body: str) -> Optional[str]:
    low = body[:8000].lower()
    if any(m in low for m in _CF_MARKERS):
        return "cloudflare_challenge"
    if any(m in low for m in _CAPTCHA_MARKERS):
        return "captcha"
    if any(m in low for m in _LOGIN_MARKERS):
        return "login_wall"
    return None


# dcinside 게시글 detail 본문 후보 selector(우선순위). 실측: static HTML에 본문 텍스트 부재
# (JS/이미지 렌더) → 아래 selector가 매칭돼도 text가 비어있음.
_DETAIL_BODY_SELECTORS = (".write_div", ".writing_view_box", ".gallview_contents", "div[itemprop=articleBody]")
_MIN_BODY_CHARS = 120   # 의미있는 본문 최소 길이(이하이면 preview-only)


@dataclass(frozen=True)
class DCInsideDetailAudit:
    source_id: str
    detail_urls_tested: tuple[str, ...]
    fetched: int
    status_codes: tuple[int, ...]
    block_marker: Optional[str]
    best_body_selector: Optional[str]
    best_body_chars: int
    body_available: bool
    conclusion: str    # DETAIL_BODY_ALIVE / DETAIL_BODY_EMPTY_STATIC / BLOCKED_NO_BYPASS / NO_DETAIL_URLS


def audit_dcinside_detail_body(
    *,
    detail_urls: list[str],
    robots_allows_detail: bool = True,
    http_get: HttpGet = _default_http_get,
    max_fetch: int = 3,
) -> DCInsideDetailAudit:
    """list에서 뽑은 detail URL들에 대해 본문 추출 가능성을 감사(우회 없음).

    robots 허용 + 차단 마커 없음 + static 본문 selector text가 _MIN_BODY_CHARS 이상이면
    DETAIL_BODY_ALIVE. 마커 있으면 BLOCKED_NO_BYPASS. static에 본문 텍스트가 없으면
    DETAIL_BODY_EMPTY_STATIC(= preview-only 유지 근거). 우회/browser 강행하지 않는다.
    """
    if not detail_urls:
        return DCInsideDetailAudit("dcinside", (), 0, (), None, None, 0, False, "NO_DETAIL_URLS")
    if not robots_allows_detail:
        return DCInsideDetailAudit("dcinside", tuple(detail_urls[:max_fetch]), 0, (), None,
                                   None, 0, False, "BLOCKED_NO_BYPASS")
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None  # type: ignore
    tested, statuses = [], []
    best_sel, best_chars = None, 0
    block_marker = None
    for url in detail_urls[:max_fetch]:
        tested.append(url)
        try:
            status, body = http_get(url)
        except Exception:
            continue
        statuses.append(status or 0)
        if status != 200 or not body:
            continue
        bm = _detect_block(body)
        if bm:
            block_marker = bm
            continue
        if BeautifulSoup is None:
            continue
        soup = BeautifulSoup(body, "lxml")
        for sel in _DETAIL_BODY_SELECTORS:
            el = soup.select_one(sel)
            if el is None:
                continue
            txt = el.get_text(" ", strip=True)
            if len(txt) > best_chars:
                best_chars, best_sel = len(txt), sel
    if block_marker:
        return DCInsideDetailAudit("dcinside", tuple(tested), len(statuses), tuple(statuses),
                                   block_marker, None, 0, False, "BLOCKED_NO_BYPASS")
    body_available = best_chars >= _MIN_BODY_CHARS
    conclusion = "DETAIL_BODY_ALIVE" if body_available else "DETAIL_BODY_EMPTY_STATIC"
    return DCInsideDetailAudit("dcinside", tuple(tested), len(statuses), tuple(statuses),
                               None, best_sel, best_chars, body_available, conclusion)


def detail_urls_from_records(records) -> list[str]:
    """community_signal record 목록 → detail(board/view) URL 목록."""
    out = []
    for r in records:
        u = r.get("source_url_or_evidence") if isinstance(r, dict) else None
        if isinstance(u, str) and _VIEW_RE.search(u):
            out.append(u)
    return out


def collect_dcinside(
    *,
    gallery_id: str = "stockus",
    minor: bool = True,
    robots_allowed: bool = True,
    http_get: HttpGet = _default_http_get,
    limit: int = 30,
) -> DCInsideStrategyResult:
    """robots 허용 갤러리 list를 static fetch해 community_signal 수집. 우회 없음.

    robots_allowed=False면 호출 자체를 하지 않는다(no-bypass).
    """
    url = list_url_for(gallery_id, minor=minor)
    if not robots_allowed:
        return DCInsideStrategyResult("dcinside", gallery_id, url, False, None,
                                      "robots_disallow", (), 0, "ROBOTS_BLOCKED_NO_BYPASS")
    try:
        status, body = http_get(url)
    except Exception as exc:
        return DCInsideStrategyResult("dcinside", gallery_id, url, False, None,
                                      f"fetch_error:{type(exc).__name__}", (), 0, "FETCH_ERROR")
    if status == 429:
        return DCInsideStrategyResult("dcinside", gallery_id, url, False, status,
                                      "rate_limited", (), 0, "EXTERNAL_RATE_LIMITED_PENDING_RESUME")
    if status != 200 or not body:
        return DCInsideStrategyResult("dcinside", gallery_id, url, False, status,
                                      f"http_{status}", (), 0, "EXTERNAL_API_ERROR_WITH_EVIDENCE")
    blocked = _detect_block(body)
    if blocked:
        verdict = {"cloudflare_challenge": "CLOUDFLARE_BLOCKED_NO_BYPASS",
                   "captcha": "CAPTCHA_BLOCKED_NO_BYPASS",
                   "login_wall": "LOGIN_BLOCKED_NO_BYPASS"}[blocked]
        return DCInsideStrategyResult("dcinside", gallery_id, url, False, status,
                                      blocked, (), 0, verdict)
    records = parse_list_rows(body, gallery_id, limit=limit)
    if not records:
        return DCInsideStrategyResult("dcinside", gallery_id, url, False, status,
                                      "no_rows_parsed", (), 0, "NEEDS_PARSER_UNRESOLVED")
    return DCInsideStrategyResult("dcinside", gallery_id, url, True, status,
                                  None, tuple(records), len(records), "COMMUNITY_SIGNAL_ALIVE")
