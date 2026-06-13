"""RSS/Atom 자동 발견 + Google News RSS 프록시 + sitemap 발견 (docs/09 기법 2·3·6).

안정성 서열(공식 API > RSS/sitemap > 숨은 JSON > selector > 휴리스틱)에서 상위 경로로
승격하기 위한 도구. 자체 feed가 없는 매체를 표준 폴백으로 온보딩한다.

- discover_feeds(html, base_url): <link rel=alternate> + 공통 경로 후보
- validate_feed(url): httpx GET → feedparser bozo==0 & entries>0
- google_news_proxy_url(domain): feed 부재 매체의 Google News RSS 우회 구독 URL
- discover_sitemaps(base_url): robots.txt Sitemap + 공통 sitemap 경로 (기법 6)
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote_plus, urljoin, urlparse

logger = logging.getLogger("ingestion.tools.feed_discovery")

_FEED_TYPES = (
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
    "application/json",
)
_COMMON_FEED_PATHS = ("/rss", "/feed", "/feed/", "/rss.xml", "/atom.xml", "/index.rss")
_COMMON_SITEMAP_PATHS = ("/sitemap.xml", "/news-sitemap.xml", "/sitemap_index.xml")


def discover_feeds(html: str, base_url: str) -> list[str]:
    """HTML <head>의 feed link + 공통 경로 후보를 절대 URL 목록으로 반환 (네트워크 없음).

    <link rel="alternate" type="application/rss+xml" href=...>를 우선 수집하고,
    하나도 없으면 공통 경로 후보(/rss, /feed 등)를 생성한다. 중복 제거, 순서 보존.
    """
    found: list[str] = []
    seen: set[str] = set()

    def _add(u: Optional[str]) -> None:
        if not u:
            return
        absolute = urljoin(base_url, u.strip())
        if absolute not in seen:
            seen.add(absolute)
            found.append(absolute)

    if html:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for link in soup.find_all("link", rel=True):
                rels = link.get("rel") or []
                rel_val = " ".join(rels).lower() if isinstance(rels, list) else str(rels).lower()
                ltype = (link.get("type") or "").lower()
                if "alternate" in rel_val and ltype in _FEED_TYPES:
                    _add(link.get("href"))
        except Exception as exc:
            logger.debug("feed link parse failed for %s: %s", base_url, exc)

    if not found:
        parsed = urlparse(base_url)
        root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else base_url
        for path in _COMMON_FEED_PATHS:
            _add(urljoin(root + "/", path.lstrip("/")))
    return found


def validate_feed(url: str, timeout: float = 15.0) -> bool:
    """httpx GET → feedparser 파싱 → bozo==0 이고 entries>0 이면 유효한 feed (네트워크 I/O)."""
    try:
        import feedparser
        import httpx
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "event-intelligence/0.7 (+ei)"})
        if resp.status_code != 200:
            return False
        parsed = feedparser.parse(resp.content)
        return getattr(parsed, "bozo", 1) == 0 and bool(parsed.entries)
    except Exception as exc:
        logger.debug("validate_feed failed for %s: %s", url, exc)
        return False


def google_news_proxy_url(domain: str, lang: str = "en-US", country: str = "US") -> str:
    """자체 feed가 없는 매체를 Google News RSS로 우회 구독하는 URL을 생성한다.

    주의(docs/09 기법 3): link는 news.google.com redirect URL이므로 canonical 해석(기법 4)이
    필요하고 evidence_level은 1단계 하향한다. Google 내부 RPC/batchexecute 우회는 하지 않는다.
    """
    domain = (domain or "").strip().lstrip("www.")
    ceid = f"{country}:{lang.split('-')[0]}"
    q = quote_plus(f"site:{domain}")
    return (
        f"https://news.google.com/rss/search?q={q}"
        f"&hl={lang}&gl={country}&ceid={quote_plus(ceid)}"
    )


def discover_sitemaps(base_url: str) -> list[str]:
    """robots.txt의 Sitemap: 줄 + 공통 sitemap 경로 후보 (기법 6).

    robots.txt 조회는 네트워크 I/O(실패 시 무시). 공통 경로는 항상 후보로 포함한다.
    깊은 백필용 — RSS가 없는 공식 기관 사이트의 폴백 발견 경로.
    """
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else base_url
    out: list[str] = []
    seen: set[str] = set()

    def _add(u: Optional[str]) -> None:
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    try:
        import httpx
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(urljoin(root + "/", "robots.txt"),
                              headers={"User-Agent": "event-intelligence/0.7 (+ei)"})
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    _add(line.split(":", 1)[1].strip())
    except Exception as exc:
        logger.debug("robots.txt fetch failed for %s: %s", root, exc)

    for path in _COMMON_SITEMAP_PATHS:
        _add(urljoin(root + "/", path.lstrip("/")))
    return out
