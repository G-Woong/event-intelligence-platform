"""소스별 payload 어댑터 (Phase E-2, 설계 02/03).

generic parser가 0분해한 **특정 소스**의 알려진 스키마를 source_id로 스코프해 매핑한다.
핵심: E-1에서 ``list``/``row``를 전역 _ARTICLE_LIST_KEYS에 넣으면 한국 공공 API가
title 없는 수만 행으로 인플레됐던 문제를, **소스별 어댑터**로 회피한다(opendart의 list는
corp_name/report_nm을 가진 정식 공시 record이므로 안전하게 매핑 가능).

원칙:
  - 없는 값을 만들지 않는다(title/url/date 없으면 None).
  - market/numeric은 candidate_total 인플레를 피하려 **단일 신호**로 환원(numeric_exempt).
  - 예외는 삼키고 None 반환(소스 격리). stdlib만 사용. 신규 설치 0.
"""
from __future__ import annotations

from typing import Any, Optional

from ingestion.orchestration.article_candidate import ArticleCandidate


def _opendart(data: dict, *, collection_status: str, confirmation_policy: Optional[str],
              raw_artifact_path: Optional[str]) -> Optional[list[ArticleCandidate]]:
    """opendart 공시 목록: {"list": [{corp_name, report_nm, rcept_no, rcept_dt, ...}]}."""
    rows = data.get("list")
    if not isinstance(rows, list):
        return None
    out: list[ArticleCandidate] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        # 정식 공시 필드가 없는 row는 매핑하지 않는다(title 없는 행 인플레 방지).
        if not (r.get("rcept_no") or r.get("corp_name") or r.get("report_nm")):
            continue
        corp = (r.get("corp_name") or "").strip()
        report = (r.get("report_nm") or "").strip()
        title = (f"{corp} {report}").strip() or (r.get("rcept_no") or None)
        rcept = r.get("rcept_no")
        url = (f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}"
               if rcept else None)
        out.append(ArticleCandidate(
            source_id="opendart", title=title or None, source_url=url,
            published_at=r.get("rcept_dt"), raw_artifact_path=raw_artifact_path,
            collection_status=collection_status, parser_name="adapter:opendart",
            confirmation_policy=confirmation_policy,
        ))
    return out or None


def _coinbase_market(data: dict, *, collection_status: str,
                     confirmation_policy: Optional[str],
                     raw_artifact_path: Optional[str]) -> Optional[list[ArticleCandidate]]:
    """coinbase products: {"products": [...]} — 수천 행을 인플레하지 않고 단일 market 신호로 환원."""
    products = data.get("products")
    if not isinstance(products, list) or not products:
        return None
    return [ArticleCandidate(
        source_id="coinbase_market",
        title=f"coinbase market products snapshot (n={len(products)})",
        raw_artifact_path=raw_artifact_path, collection_status=collection_status,
        numeric_payload_exempt=True, parser_name="adapter:coinbase_market",
        confirmation_policy=confirmation_policy,
    )]


def _binance_market(data: list, *, collection_status: str,
                    confirmation_policy: Optional[str],
                    raw_artifact_path: Optional[str]) -> Optional[list[ArticleCandidate]]:
    """binance 24h ticker: [{symbol, lastPrice, ...}, ...] — 수천 행을 단일 market 신호로 환원.

    coinbase와 동일 원칙: 거래소 스냅샷 행을 candidate_total로 폭증시키지 않는다(인플레 금지).
    """
    if not isinstance(data, list) or not data or not all(isinstance(x, dict) for x in data):
        return None
    return [ArticleCandidate(
        source_id="binance_market",
        title=f"binance market tickers snapshot (n={len(data)})",
        raw_artifact_path=raw_artifact_path, collection_status=collection_status,
        numeric_payload_exempt=True, parser_name="adapter:binance_market",
        confirmation_policy=confirmation_policy,
    )]


# dict payload 어댑터
_ADAPTERS = {
    "opendart": _opendart,
    "coinbase_market": _coinbase_market,
}
# list payload 어댑터(거래소 스냅샷 등 numeric 행 환원)
_LIST_ADAPTERS = {
    "binance_market": _binance_market,
}


def adapt_source_payload(
    source_id: str, data: Any, *, collection_status: str = "LIVE_SUCCESS",
    confirmation_policy: Optional[str] = None, raw_artifact_path: Optional[str] = None,
) -> Optional[tuple[list[ArticleCandidate], str]]:
    """source_id 어댑터로 candidate 추출. 어댑터 없거나 0건이면 None(generic fallback 유지).

    dict/list payload 모두 지원(opendart/coinbase=dict, binance=list).
    """
    if isinstance(data, dict):
        fn = _ADAPTERS.get(source_id)
    elif isinstance(data, list):
        fn = _LIST_ADAPTERS.get(source_id)
    else:
        fn = None
    if fn is None:
        return None
    try:
        cands = fn(data, collection_status=collection_status,
                   confirmation_policy=confirmation_policy,
                   raw_artifact_path=raw_artifact_path)
    except Exception:
        return None
    if not cands:
        return None
    return cands, (cands[0].parser_name or f"adapter:{source_id}")
