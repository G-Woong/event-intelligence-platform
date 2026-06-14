"""Artifact → ArticleCandidate 파서 (Phase D-2, 설계 04/05).

수집 artifact(raw_payload/raw_signal/extracted_text)를 읽어 개별 기사 후보로 분해한다.
지원: GDELT JSON / RSS·Atom XML / generic JSON list / generic JSON dict(articles·results·items)
/ numeric·API payload / extracted-text fallback / no-artifact / malformed.

원칙: **없는 값은 만들지 않는다**(title/url/body 없으면 None). 파싱 실패는 cycle을 죽이지 않고
``parse_error``로 보존한다. 실제 기사 전문을 저장/생성하지 않는다(synthetic/실측 artifact 참조만).

stdlib만 사용(json, xml.etree). 신규 설치 0.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any, Optional

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.canonical_url import canonicalize_url

# 기사 dict의 후보 컨테이너 키(우선순위 순).
_ARTICLE_LIST_KEYS = ("articles", "results", "items", "stories", "docs", "data", "hits")
# 필드 매핑(없는 값은 None — 첫 매칭만 사용).
_TITLE_KEYS = ("title", "headline", "name")
_URL_KEYS = ("url", "link", "webUrl", "web_url", "guid")
_TIME_KEYS = ("published_at", "publishedAt", "pubDate", "seendate", "date",
              "webPublicationDate", "published", "updated", "created_at")
_SUMMARY_KEYS = ("summary", "description", "abstract", "snippet", "contentSnippet",
                 "content")
_BODY_KEYS = ("body", "full_text", "articleBody", "bodyText", "text")
# numeric/API payload 식별 키.
_NUMERIC_KEYS = frozenset({
    "price", "symbol", "value", "ticker", "last", "bid", "ask", "close",
    "open", "high", "low", "c", "o", "h", "l", "pc", "amount", "quote",
})
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _first(d: dict, keys: tuple[str, ...]) -> Optional[str]:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return _clean(d[k])
    return None


def _make_candidate(
    *, source_id: str, collection_status: str, confirmation_policy: Optional[str],
    parser_name: str, title: Optional[str] = None, source_url: Optional[str] = None,
    published_at: Optional[str] = None, summary: Optional[str] = None,
    body_text: Optional[str] = None, raw_artifact_path: Optional[str] = None,
    extracted_text_ref: Optional[str] = None, numeric_payload_exempt: bool = False,
    parse_error: Optional[str] = None,
) -> ArticleCandidate:
    body = _clean(body_text)
    body_missing = body is None
    return ArticleCandidate(
        source_id=source_id,
        title=_clean(title),
        source_url=_clean(source_url),
        published_at=_clean(published_at),
        summary=_clean(summary),
        body_text=body,
        raw_artifact_path=raw_artifact_path,
        extracted_text_ref=extracted_text_ref,
        canonical_url=canonicalize_url(source_url),  # no-network
        body_missing=body_missing,
        collection_status=collection_status,
        parser_name=parser_name,
        parse_error=parse_error,
        numeric_payload_exempt=numeric_payload_exempt,
        confirmation_policy=confirmation_policy,
    )


def _article_from_item(item: dict, *, source_id, collection_status,
                       confirmation_policy, parser_name, raw_artifact_path) -> ArticleCandidate:
    return _make_candidate(
        source_id=source_id, collection_status=collection_status,
        confirmation_policy=confirmation_policy, parser_name=parser_name,
        title=_first(item, _TITLE_KEYS), source_url=_first(item, _URL_KEYS),
        published_at=_first(item, _TIME_KEYS), summary=_first(item, _SUMMARY_KEYS),
        body_text=_first(item, _BODY_KEYS), raw_artifact_path=raw_artifact_path,
    )


def _looks_numeric(d: dict) -> bool:
    return any(k in d for k in _NUMERIC_KEYS)


def parse_artifact_text(
    text: str,
    *,
    source_id: str,
    collection_status: str = "LIVE_SUCCESS",
    confirmation_policy: Optional[str] = None,
    raw_artifact_path: Optional[str] = None,
    fmt: Optional[str] = None,
) -> tuple[list[ArticleCandidate], str, list[str]]:
    """artifact 텍스트 → (candidates, parser_name, errors).

    fmt(json|xml|extracted_text)을 명시하지 않으면 내용으로 추정한다. 빈 텍스트는
    ([], "empty", ["empty_artifact"]). 파싱 실패는 ([], "<fmt>_malformed", [err]).
    """
    if text is None or not text.strip():
        return [], "empty", ["empty_artifact"]

    detected = fmt or _sniff(text)
    if detected == "json":
        return _parse_json(text, source_id=source_id, collection_status=collection_status,
                           confirmation_policy=confirmation_policy,
                           raw_artifact_path=raw_artifact_path)
    if detected == "html":
        # HTML 페이지의 기사-level 분해는 Phase D 범위 밖(설계 04: 본문 cascade가 담당).
        # XML 파서로 억지로 보내지 않고 정직하게 미지원 fallback으로 보고한다(사건은 보존됨).
        return [], "html_unsupported", ["html_parsing_deferred_phase_d"]
    if detected == "xml":
        return _parse_xml(text, source_id=source_id, collection_status=collection_status,
                          confirmation_policy=confirmation_policy,
                          raw_artifact_path=raw_artifact_path)
    return _parse_extracted_text(text, source_id=source_id,
                                 collection_status=collection_status,
                                 confirmation_policy=confirmation_policy,
                                 raw_artifact_path=raw_artifact_path)


def _sniff(text: str) -> str:
    stripped = text.lstrip()
    head = stripped[:1]
    if head in ("{", "["):
        return "json"
    if head == "<":
        # HTML 문서는 XML well-formed가 아니어서 XML 파서로 보내면 오분류된다.
        lowered = stripped[:200].lower()
        if "<!doctype html" in lowered or "<html" in lowered:
            return "html"
        return "xml"
    return "extracted_text"


def _parse_json(text, *, source_id, collection_status, confirmation_policy,
                raw_artifact_path):
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        return [], "json_malformed", [f"json decode error: {exc}"]

    # list → generic article list
    if isinstance(data, list):
        cands = [
            _article_from_item(it, source_id=source_id, collection_status=collection_status,
                               confirmation_policy=confirmation_policy,
                               parser_name="generic_json_list", raw_artifact_path=raw_artifact_path)
            for it in data if isinstance(it, dict)
        ]
        if not cands:
            return [], "generic_json_list", ["no_dict_items"]
        return cands, "generic_json_list", []

    if isinstance(data, dict):
        # 기사 컨테이너 탐색
        for key in _ARTICLE_LIST_KEYS:
            container = data.get(key)
            if isinstance(container, list) and any(isinstance(x, dict) for x in container):
                # GDELT는 articles + seendate/domain 특성으로 식별
                is_gdelt = key == "articles" and any(
                    isinstance(x, dict) and ("seendate" in x or "domain" in x)
                    for x in container
                )
                parser_name = "gdelt" if is_gdelt else f"generic_json_dict:{key}"
                cands = [
                    _article_from_item(it, source_id=source_id,
                                       collection_status=collection_status,
                                       confirmation_policy=confirmation_policy,
                                       parser_name=parser_name,
                                       raw_artifact_path=raw_artifact_path)
                    for it in container if isinstance(it, dict)
                ]
                return cands, parser_name, []
        # 기사 컨테이너 없음 → numeric/API payload
        if _looks_numeric(data):
            cand = _make_candidate(
                source_id=source_id, collection_status=collection_status,
                confirmation_policy=confirmation_policy, parser_name="numeric_payload",
                title=_first(data, _TITLE_KEYS),
                summary=_first(data, ("symbol", "ticker")),
                raw_artifact_path=raw_artifact_path, numeric_payload_exempt=True,
            )
            return [cand], "numeric_payload", []
        # 인식 불가한 dict → source-level fallback(빈 후보 아님, 단서 보존 없음 → 보고)
        return [], "json_unrecognized", ["no_article_container_and_not_numeric"]

    # 스칼라 JSON(숫자/문자열) → numeric 신호
    cand = _make_candidate(
        source_id=source_id, collection_status=collection_status,
        confirmation_policy=confirmation_policy, parser_name="numeric_payload",
        raw_artifact_path=raw_artifact_path, numeric_payload_exempt=True,
    )
    return [cand], "numeric_payload", []


def _parse_xml(text, *, source_id, collection_status, confirmation_policy,
               raw_artifact_path):
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return [], "xml_malformed", [f"xml parse error: {exc}"]

    cands: list[ArticleCandidate] = []
    # RSS <item>
    items = root.findall(".//item")
    for it in items:
        cands.append(_make_candidate(
            source_id=source_id, collection_status=collection_status,
            confirmation_policy=confirmation_policy, parser_name="rss",
            title=it.findtext("title"), source_url=it.findtext("link"),
            published_at=it.findtext("pubDate"), summary=it.findtext("description"),
            raw_artifact_path=raw_artifact_path,
        ))
    if cands:
        return cands, "rss", []

    # Atom <entry>
    entries = root.findall(f".//{_ATOM_NS}entry")
    for en in entries:
        link_el = en.find(f"{_ATOM_NS}link")
        href = link_el.get("href") if link_el is not None else None
        published = en.findtext(f"{_ATOM_NS}updated") or en.findtext(f"{_ATOM_NS}published")
        cands.append(_make_candidate(
            source_id=source_id, collection_status=collection_status,
            confirmation_policy=confirmation_policy, parser_name="atom",
            title=en.findtext(f"{_ATOM_NS}title"), source_url=href,
            published_at=published, summary=en.findtext(f"{_ATOM_NS}summary"),
            raw_artifact_path=raw_artifact_path,
        ))
    if cands:
        return cands, "atom", []

    return [], "xml_no_items", ["no_item_or_entry_elements"]


def _parse_extracted_text(text, *, source_id, collection_status, confirmation_policy,
                          raw_artifact_path):
    """save_extracted_text 포맷(header 줄 + '---' + body) → 단일 후보."""
    title = url = published = None
    body = text
    lines = text.splitlines(keepends=True)
    # header는 save_extracted_text 포맷의 '---' **단독 줄**에서만 끝난다(본문 내 '---' 무시).
    sep_idx = next((i for i, ln in enumerate(lines) if ln.strip() == "---"), None)
    if sep_idx is not None:
        header_lines = lines[:sep_idx]
        # header에 기대 키가 하나라도 있어야 헤더로 인정(아니면 전체를 body로).
        parsed = {}
        for ln in header_lines:
            key, sep, val = ln.partition(":")
            if not sep:
                continue
            parsed[key.strip().lower()] = val.strip()
        if parsed.keys() & {"title", "source_url", "published_at"}:
            title = parsed.get("title") or None
            url = parsed.get("source_url") or None
            published = parsed.get("published_at") or None
            body = "".join(lines[sep_idx + 1:])
    cand = _make_candidate(
        source_id=source_id, collection_status=collection_status,
        confirmation_policy=confirmation_policy, parser_name="extracted_text",
        title=title, source_url=url, published_at=published, body_text=body,
        extracted_text_ref=raw_artifact_path,
    )
    return [cand], "extracted_text", []
