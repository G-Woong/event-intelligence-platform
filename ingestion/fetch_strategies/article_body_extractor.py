"""본문 추출 캐스케이드: trafilatura → readability → DOM 휴리스틱.

각 단계는 실패(예외/빈 본문/200자 미만) 시 다음 단계로 폴백한다.
반환: {"title", "body", "method"} 또는 None. 네트워크 호출 없음 (html 입력 전제).

기존 추출기(`extract_with_*`)를 감싸 통일된 캐스케이드로 제공한다 — 새 추출 로직을
만들지 않고 기존 자산을 재사용한다.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("ingestion.fetch_strategies.article_body_extractor")
_MIN_BODY_CHARS = 200
# site가 명시한 본문 영역 selector는 boilerplate가 아님이 보장되므로 낮은 임계 허용
# (커뮤니티 글은 짧은 경우가 많다 — readability가 공통 안내 박스를 오선택하는 문제 회피).
_MIN_SITE_SELECTOR_CHARS = 50


def _normalize(result) -> Optional[dict]:
    """ExtractionResult → {"title","body"} 또는 None (body 없으면)."""
    if result is None or not getattr(result, "body", None):
        return None
    return {"title": result.title, "body": result.body}


def _try_trafilatura(html: str, url: str) -> Optional[dict]:
    from ingestion.tools.trafilatura_extractor import extract_with_trafilatura
    return _normalize(extract_with_trafilatura(html, url))


def _try_readability(html: str, url: str) -> Optional[dict]:
    from ingestion.tools.readability_extractor import extract_with_readability
    return _normalize(extract_with_readability(html, url))


def _try_dom_heuristic(html: str, url: str) -> Optional[dict]:
    from ingestion.tools.dom_candidate_extractor import extract_with_dom_heuristic
    return _normalize(extract_with_dom_heuristic(html, url))


def _try_site_selectors(html: str, body_selectors: list) -> tuple[bool, Optional[dict]]:
    """site spec이 지정한 본문 영역 selector로 직접 추출 (boilerplate 회피).

    반환: (matched, result). matched=본문 컨테이너 selector가 페이지에서 매칭됐는지,
    result=내용이 충분(≥임계)하면 {"title","body","method"} 아니면 None.

    범용 추출기(trafilatura/readability)가 커뮤니티 페이지의 공통 안내 박스를
    본문으로 오선택하는 문제를, site가 명시한 본문 컨테이너로 우선 해결한다.
    """
    if not body_selectors:
        return False, None
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return False, None
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    matched = False
    for sel in body_selectors:
        try:
            el = soup.select_one(sel)
        except Exception:
            continue
        if el is None:
            continue
        matched = True
        body = el.get_text(separator="\n", strip=True)
        if body and len(body) >= _MIN_SITE_SELECTOR_CHARS:
            return True, {"title": title, "body": body, "method": "site_selector"}
    return matched, None


def extract_article_body(html: str, url: str, body_selectors: Optional[list] = None) -> Optional[dict]:
    if not html:
        return None
    # site가 지정한 본문 selector를 cascade보다 우선 — 커뮤니티 boilerplate 오선택 방지
    if body_selectors:
        matched, site_out = _try_site_selectors(html, body_selectors)
        if site_out:
            return site_out
        if matched:
            # 본문 컨테이너는 찾았으나 내용이 너무 짧음 = 본문 없음.
            # cascade는 공통 안내(boilerplate)를 오선택하므로 폴백하지 않는다.
            return None
        # 컨테이너 자체가 없음 = 예상과 다른 페이지 구조 → cascade로 폴백
    for method, fn in (
        ("trafilatura", _try_trafilatura),
        ("readability", _try_readability),
        ("dom_heuristic", _try_dom_heuristic),
    ):
        try:
            out = fn(html, url)
        except Exception as exc:
            logger.debug("%s failed for %s: %s", method, url, exc)
            continue
        if out and out.get("body") and len(out["body"]) >= _MIN_BODY_CHARS:
            out["method"] = method
            return out
    return None
