"""소스 콘텐츠 타입 분류 — body 추출 기대치의 단일 출처(사용자 판정 기준).

문제: official_record 소스를 한 덩어리로 보면, 카탈로그형 메타데이터 API(영화/도서/공연/관광/
박스오피스/게임 — 별도 산문 본문이 없음)가 "본문 미추출(BODY_MISSING/SNIPPET_ONLY)"로 잘못
실패 처리된다. 이들은 API 메타(제목+개요/설명)가 곧 완성 record다.

판정 기준(사용자 지정):
  - article / document / detail page  → body_expected=True   (실제 산문 본문 추출 대상)
  - catalog / metadata API            → body_expected=False, metadata_complete=True
                                        (snippet/description/overview/summary = metadata_summary, body 아님)
  - search API                        → url_candidate=True   (downstream body fetch 별도)
  - community / list                  → body_expected=conditional (corroboration 후 판단)
  - structured / numeric              → body_expected=False  (schema 수집이 성공)

stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from typing import Optional

# ── 명시 오버라이드(소스별 콘텐츠 성격이 source_group만으로 안 드러나는 경우) ──────────
# 실제 산문 본문이 있는 공식 문서/상세 페이지(body ladder 대상).
_DOCUMENT = frozenset({"opendart", "sec_edgar", "federal_register"})
_DETAIL = frozenset({"culture_info"})
# 카탈로그형 메타데이터 API — 별도 산문 본문 없음. snippet=metadata_summary(완성), 실패 아님.
_CATALOG = frozenset({"aladin", "tmdb", "kofic", "kopis", "tour", "igdb"})

# source_group → 기본 콘텐츠 타입(오버라이드에 없는 소스).
_GROUP_DEFAULT = {
    "news": "article",
    "domain": "article",
    "official": "document",     # 공식 그룹 기본은 document, 단 _CATALOG/_DETAIL 오버라이드 우선
    "search": "search",
    "community": "community",
    "market": "structured",
    "trend": "structured",
}

# body_expected=True 인 타입(실제 산문 본문 추출 대상).
_BODY_EXPECTED = frozenset({"article", "document", "detail"})
# metadata_complete=True 인 타입(메타/스키마 수집 자체가 성공 — body 미추출이 실패 아님).
_METADATA_COMPLETE = frozenset({"catalog_metadata", "structured"})

# 분류 라벨(최종 매트릭스 판정용).
CLASS_BODY_EXPECTED = "BODY_EXPECTED"
CLASS_METADATA_COMPLETE = "METADATA_COMPLETE"      # 카탈로그/구조화 = 수집 성공
CLASS_URL_CANDIDATE = "URL_CANDIDATE"              # 검색 = downstream 별도
CLASS_COMMUNITY_CONDITIONAL = "COMMUNITY_CONDITIONAL"


def content_type(source_id: str, source_group: Optional[str] = None) -> str:
    """소스의 콘텐츠 타입을 반환.

    article / document / detail / catalog_metadata / search / community / structured.
    명시 오버라이드(_DOCUMENT/_DETAIL/_CATALOG)가 source_group 기본값보다 우선한다.
    """
    if source_id in _CATALOG:
        return "catalog_metadata"
    if source_id in _DOCUMENT:
        return "document"
    if source_id in _DETAIL:
        return "detail"
    return _GROUP_DEFAULT.get(source_group or "", "article")


def body_expected(source_id: str, source_group: Optional[str] = None) -> bool:
    """실제 산문 본문 추출이 기대되는가(article/document/detail)."""
    return content_type(source_id, source_group) in _BODY_EXPECTED


def is_metadata_complete(source_id: str, source_group: Optional[str] = None) -> bool:
    """카탈로그/구조화 — 메타/스키마 수집 자체가 완성(본문 미추출이 실패 아님)."""
    return content_type(source_id, source_group) in _METADATA_COMPLETE


def is_url_candidate(source_id: str, source_group: Optional[str] = None) -> bool:
    """검색 API — URL 후보 확보가 1차 성공, body는 downstream 별도."""
    return content_type(source_id, source_group) == "search"


def classify(source_id: str, source_group: Optional[str] = None) -> str:
    """최종 매트릭스 판정 라벨(BODY_EXPECTED/METADATA_COMPLETE/URL_CANDIDATE/COMMUNITY_CONDITIONAL)."""
    ct = content_type(source_id, source_group)
    if ct in _BODY_EXPECTED:
        return CLASS_BODY_EXPECTED
    if ct in _METADATA_COMPLETE:
        return CLASS_METADATA_COMPLETE
    if ct == "search":
        return CLASS_URL_CANDIDATE
    return CLASS_COMMUNITY_CONDITIONAL


# 본문 추출 ladder를 연결할 소스(실제 산문 본문 기대) — nyt/opendart/culture_info + 기타 article.
def body_ladder_eligible(source_id: str, source_group: Optional[str] = None) -> bool:
    """body ladder(rescue_news_body) 연결 대상인가. catalog/structured/search는 제외."""
    return body_expected(source_id, source_group)
