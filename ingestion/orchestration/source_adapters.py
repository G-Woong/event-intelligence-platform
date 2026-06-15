"""소스별 payload 어댑터 (Phase E-2/E-3, 설계 02/03).

generic parser가 0분해(또는 title-less 인플레)한 **특정 소스**의 알려진 스키마를 source_id로
스코프해 매핑한다. 핵심: 전역 컨테이너 키(list/row/items/results)를 넓히면 한국 공공 API가
title 없는 수만 행으로 인플레됐던 문제를, **소스별 어댑터**로 회피한다.

E-3 추가: NEEDS_PARSER로 남았던 source들의 실제 live 스키마를 어댑터로 흡수한다
  - JSON: sec_edgar / twelve_data / alpha_vantage / tour / kofic / tmdb / aladin /
          serper / youtube / product_hunt / its(reduce)
  - XML : kopis / culture_info
generic 컨테이너 탐지보다 **선제(pre-empt)** 호출되어(artifact_parser), youtube/tmdb/its처럼
top-level items/results를 가진 source가 title-less로 분해되는 것을 막는다.

원칙:
  - 없는 값을 만들지 않는다(title/url/date 없으면 None).
  - market/numeric/대량 행은 candidate_total 인플레를 피하려 **단일 신호**로 환원(numeric_exempt).
  - 예외는 삼키고 None 반환(소스 격리). stdlib만 사용. 신규 설치 0.
"""
from __future__ import annotations

from typing import Any, Optional

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.canonical_url import canonicalize_url


def _cand(source_id: str, parser: str, *, collection_status: str,
          confirmation_policy: Optional[str], raw_artifact_path: Optional[str],
          title: Optional[str] = None, source_url: Optional[str] = None,
          published_at: Optional[str] = None, summary: Optional[str] = None,
          numeric_payload_exempt: bool = False) -> ArticleCandidate:
    """어댑터 공통 candidate 생성(canonical_url은 no-network 정규화)."""
    t = (title or "").strip() or None
    u = (source_url or "").strip() or None
    return ArticleCandidate(
        source_id=source_id, title=t, source_url=u,
        published_at=(published_at or None), summary=(summary or None),
        canonical_url=canonicalize_url(u) if u else None,
        raw_artifact_path=raw_artifact_path, collection_status=collection_status,
        numeric_payload_exempt=numeric_payload_exempt,
        parser_name=parser, confirmation_policy=confirmation_policy,
    )


# ── 기존(E-2) ────────────────────────────────────────────────────────────────
def _opendart(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
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
        url = (f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}" if rcept else None)
        out.append(_cand("opendart", "adapter:opendart", title=title,
                         source_url=url, published_at=r.get("rcept_dt"), **kw))
    return out or None


def _coinbase_market(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """coinbase products: {"products": [...]} — 수천 행을 단일 market 신호로 환원."""
    products = data.get("products")
    if not isinstance(products, list) or not products:
        return None
    return [_cand("coinbase_market", "adapter:coinbase_market",
                  title=f"coinbase market products snapshot (n={len(products)})",
                  numeric_payload_exempt=True, **kw)]


def _binance_market(data: list, **kw) -> Optional[list[ArticleCandidate]]:
    """binance 24h ticker: [{symbol, lastPrice, ...}] — 수천 행을 단일 market 신호로 환원."""
    if not isinstance(data, list) or not data or not all(isinstance(x, dict) for x in data):
        return None
    return [_cand("binance_market", "adapter:binance_market",
                  title=f"binance market tickers snapshot (n={len(data)})",
                  numeric_payload_exempt=True, **kw)]


# ── E-3: official record 어댑터 ───────────────────────────────────────────────
def _sec_edgar(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """SEC EDGAR full-text search: {"hits": {"hits": [{_id, _source: {...}}]}}.

    _source.display_names + form → title, adsh+cik → 안정 filing index URL, file_date → 시각.
    """
    hits = data.get("hits")
    inner = hits.get("hits") if isinstance(hits, dict) else None
    if not isinstance(inner, list) or not inner:
        return None
    out: list[ArticleCandidate] = []
    for h in inner:
        if not isinstance(h, dict):
            continue
        src = h.get("_source") if isinstance(h.get("_source"), dict) else {}
        names = src.get("display_names")
        label = names[0] if isinstance(names, list) and names else None
        form = src.get("form")
        title = " ".join(x for x in [label, form] if x) or h.get("_id")
        adsh = src.get("adsh")
        ciks = src.get("ciks")
        cik = ciks[0] if isinstance(ciks, list) and ciks else None
        url = None
        if adsh:
            nodash = str(adsh).replace("-", "")
            cik_part = str(int(cik)) if (cik and str(cik).isdigit()) else (cik or "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik_part}/{nodash}/{adsh}-index.htm"
        out.append(_cand("sec_edgar", "adapter:sec_edgar", title=title,
                         source_url=url, published_at=src.get("file_date"), **kw))
    return out or None


def _tour(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """한국관광공사 TourAPI: response.body.items.item[] (title, contentid, modifiedtime)."""
    item = (((data.get("response") or {}).get("body") or {}).get("items") or {})
    rows = item.get("item") if isinstance(item, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    out: list[ArticleCandidate] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        cid = r.get("contentid")
        url = (f"https://korean.visitkorea.or.kr/detail/ms_detail.do?cotId={cid}" if cid else None)
        out.append(_cand("tour", "adapter:tour", title=r.get("title"),
                         source_url=url, published_at=r.get("modifiedtime") or r.get("createdtime"),
                         summary=r.get("addr1"), **kw))
    return out or None


def _kofic(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """영화관입장권통합전산망(KOFIC) 일별 박스오피스: dailyBoxOfficeList[] (movieNm, movieCd, salesAmt)."""
    box = data.get("boxOfficeResult")
    rows = box.get("dailyBoxOfficeList") if isinstance(box, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    show = (box.get("showRange") or "").split("~")[0].strip() or None
    out: list[ArticleCandidate] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        code = r.get("movieCd")
        url = (f"https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieInfo.do?code={code}"
               if code else None)
        out.append(_cand("kofic", "adapter:kofic", title=r.get("movieNm"),
                         source_url=url, published_at=show,
                         summary=f"rank={r.get('rank')} salesAmt={r.get('salesAmt')}", **kw))
    return out or None


def _tmdb(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """TMDB results[]: id → 안정 URL, title/name, release_date/first_air_date → 시각."""
    rows = data.get("results")
    if not isinstance(rows, list) or not rows:
        return None
    out: list[ArticleCandidate] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        mid = r.get("id")
        kind = "tv" if (r.get("first_air_date") or r.get("name")) and not r.get("title") else "movie"
        url = f"https://www.themoviedb.org/{kind}/{mid}" if mid else None
        out.append(_cand("tmdb", "adapter:tmdb", title=r.get("title") or r.get("name"),
                         source_url=url,
                         published_at=r.get("release_date") or r.get("first_air_date"),
                         summary=r.get("overview"), **kw))
    return out or None


def _aladin(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """알라딘 상품 검색: item[] (title, link, pubDate)."""
    rows = data.get("item")
    if not isinstance(rows, list) or not rows:
        return None
    out: list[ArticleCandidate] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(_cand("aladin", "adapter:aladin", title=r.get("title"),
                         source_url=r.get("link"), published_at=r.get("pubDate"),
                         summary=r.get("author"), **kw))
    return out or None


# ── E-3: search / community 어댑터 ───────────────────────────────────────────
def _serper(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """Serper Google search: organic[] (title, link, snippet, date)."""
    rows = data.get("organic")
    if not isinstance(rows, list) or not rows:
        return None
    out: list[ArticleCandidate] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(_cand("serper", "adapter:serper", title=r.get("title"),
                         source_url=r.get("link"), published_at=r.get("date"),
                         summary=r.get("snippet"), **kw))
    return out or None


def _youtube(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """YouTube search.list: items[].snippet.title + id.videoId → watch URL + publishedAt."""
    rows = data.get("items")
    if not isinstance(rows, list) or not rows:
        return None
    out: list[ArticleCandidate] = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        sn = it.get("snippet") if isinstance(it.get("snippet"), dict) else {}
        idobj = it.get("id")
        vid = idobj.get("videoId") if isinstance(idobj, dict) else None
        url = f"https://www.youtube.com/watch?v={vid}" if vid else None
        out.append(_cand("youtube", "adapter:youtube", title=sn.get("title"),
                         source_url=url, published_at=sn.get("publishedAt"),
                         summary=sn.get("description"), **kw))
    return out or None


def _product_hunt(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """Product Hunt GraphQL: data.posts.edges[].node.name (url/date는 쿼리 미요청 → None, degraded)."""
    posts = ((data.get("data") or {}).get("posts") or {})
    edges = posts.get("edges") if isinstance(posts, dict) else None
    if not isinstance(edges, list) or not edges:
        return None
    out: list[ArticleCandidate] = []
    for e in edges:
        node = e.get("node") if isinstance(e, dict) else None
        if not isinstance(node, dict):
            continue
        # G-5 anchor 보강: url 우선, 없으면 slug 기반 결정적 post URL(NO_STABLE_URL 해소).
        url = node.get("url")
        slug = node.get("slug") or _slugify(node.get("name"))
        if not url and slug:
            url = f"https://www.producthunt.com/posts/{slug}"
        out.append(_cand("product_hunt", "adapter:product_hunt", title=node.get("name"),
                         source_url=url, published_at=node.get("createdAt") or node.get("featuredAt"),
                         summary=node.get("tagline"), **kw))
    return out or None


def _slugify(name: Optional[str]) -> Optional[str]:
    """name → producthunt slug 근사(소문자/공백→하이픈/영숫자만)."""
    if not name:
        return None
    import re as _re
    s = _re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return s or None


# ── E-3: 대량 numeric 환원 어댑터 ─────────────────────────────────────────────
def _twelve_data(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """Twelve Data time_series: meta + values[] OHLCV → 최신 1개 structured 신호."""
    values = data.get("values")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    if not isinstance(values, list) or not values or not isinstance(values[0], dict):
        return None
    latest = values[0]
    sym = meta.get("symbol")
    dt = latest.get("datetime")
    title = f"twelve_data {sym} close={latest.get('close')} @ {dt}"
    return [_cand("twelve_data", "adapter:twelve_data", title=title,
                  published_at=dt, numeric_payload_exempt=True, **kw)]


def _alpha_vantage(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """Alpha Vantage Time Series (Daily): {date: OHLCV} → 최신 1개 structured 신호."""
    ts = data.get("Time Series (Daily)")
    meta = data.get("Meta Data") if isinstance(data.get("Meta Data"), dict) else {}
    if not isinstance(ts, dict) or not ts:
        return None
    latest = max(ts.keys())
    row = ts.get(latest) if isinstance(ts.get(latest), dict) else {}
    sym = meta.get("2. Symbol")
    title = f"alpha_vantage {sym} close={row.get('4. close')} @ {latest}"
    return [_cand("alpha_vantage", "adapter:alpha_vantage", title=title,
                  published_at=latest, numeric_payload_exempt=True, **kw)]


def _its(data: dict, **kw) -> Optional[list[ArticleCandidate]]:
    """ITS 도로 소통정보: body.items[] 수만 링크 → 단일 snapshot 신호(31587행 인플레 방지).

    개별 도로 link 속도는 '사건' 단위가 아니다 — 인플레만 막고 finalize에서 서비스 가치 판정.
    """
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    items = body.get("items")
    if not isinstance(items, list) or not items:
        return None
    return [_cand("its", "adapter:its",
                  title=f"its road traffic snapshot (n={len(items)} links)",
                  numeric_payload_exempt=True, **kw)]


# ── E-3: XML 어댑터(kopis/culture_info) ──────────────────────────────────────
def _xml_kopis(root, **kw) -> Optional[list[ArticleCandidate]]:
    """KOPIS 공연목록 XML: <dbs><db><mt20id/prfnm/prfpdfrom/...>."""
    dbs = root.findall(".//db")
    if not dbs:
        return None
    out: list[ArticleCandidate] = []
    for db in dbs:
        mid = db.findtext("mt20id")
        url = (f"https://www.kopis.or.kr/por/db/pblprfr/selectPblprfrView.do?mt20id={mid}"
               if mid else None)
        out.append(_cand("kopis", "adapter:kopis", title=db.findtext("prfnm"),
                         source_url=url, published_at=db.findtext("prfpdfrom"),
                         summary=db.findtext("fcltynm"), **kw))
    return out or None


def _xml_culture_info(root, **kw) -> Optional[list[ArticleCandidate]]:
    """문화포털 공연/전시 XML: <response><body><items><item><title/startDate/place/...>."""
    items = root.findall(".//items/item")
    if not items:
        return None
    out: list[ArticleCandidate] = []
    for it in items:
        # G-5 anchor 보강: 실제 url 우선, 없으면 seq 기반 결정적 detail URL(NO_STABLE_URL 해소).
        url = it.findtext("url") or it.findtext("referenceUrl") or None
        seq = it.findtext("seq") or it.findtext("serviceId")
        if not url and seq:
            url = f"https://www.culture.go.kr/wantU/detailView.do?seq={seq}"
        out.append(_cand("culture_info", "adapter:culture_info", title=it.findtext("title"),
                         source_url=url, published_at=it.findtext("startDate"),
                         summary=it.findtext("place"), **kw))
    return out or None


# dict payload 어댑터
_ADAPTERS = {
    "opendart": _opendart,
    "coinbase_market": _coinbase_market,
    "sec_edgar": _sec_edgar,
    "tour": _tour,
    "kofic": _kofic,
    "tmdb": _tmdb,
    "aladin": _aladin,
    "serper": _serper,
    "youtube": _youtube,
    "product_hunt": _product_hunt,
    "twelve_data": _twelve_data,
    "alpha_vantage": _alpha_vantage,
    "its": _its,
}
# list payload 어댑터(거래소 스냅샷 등 numeric 행 환원)
_LIST_ADAPTERS = {
    "binance_market": _binance_market,
}
# XML root 어댑터(RSS/Atom이 아닌 소스별 커스텀 XML)
_XML_ADAPTERS = {
    "kopis": _xml_kopis,
    "culture_info": _xml_culture_info,
}


def adapt_source_payload(
    source_id: str, data: Any, *, collection_status: str = "LIVE_SUCCESS",
    confirmation_policy: Optional[str] = None, raw_artifact_path: Optional[str] = None,
) -> Optional[tuple[list[ArticleCandidate], str]]:
    """source_id 어댑터로 candidate 추출. 어댑터 없거나 0건이면 None(generic fallback 유지).

    dict/list payload 모두 지원. artifact_parser가 generic 컨테이너 탐지보다 **선제** 호출한다.
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


def adapt_source_xml(
    source_id: str, root, *, collection_status: str = "LIVE_SUCCESS",
    confirmation_policy: Optional[str] = None, raw_artifact_path: Optional[str] = None,
) -> Optional[tuple[list[ArticleCandidate], str]]:
    """source_id XML 어댑터로 candidate 추출(RSS/Atom 실패 후 호출). 없으면 None."""
    fn = _XML_ADAPTERS.get(source_id)
    if fn is None:
        return None
    try:
        cands = fn(root, collection_status=collection_status,
                   confirmation_policy=confirmation_policy,
                   raw_artifact_path=raw_artifact_path)
    except Exception:
        return None
    if not cands:
        return None
    return cands, (cands[0].parser_name or f"adapter:{source_id}")
