"""Phase G-4 Vendor official API route builders — 우회 없이 공식 API로 데이터 확보.

bok_ecos/eia/kma/nyt는 Phase F에서 VENDOR_CONTRACT_REQUIRED/EXTERNAL_API_ERROR로 남았다.
원인은 우회 차단이 아니라 **공식 API route/params 미구현**이었다(웹 스크래핑이 403, catalog
endpoint 호출 등). 이 모듈은 각 vendor의 **공식 data API**를 올바른 params로 호출해 정규화한다.

원칙(우회 금지/보안):
- API key는 env_loader로만 읽고 값을 로그/출력/직렬화하지 않는다. 요청 URL에만 쓴다.
- evidence URL은 **key를 제거한** 안정 참조 URL로 만든다(raw_events.url NOT NULL 충족 + 재현 가능).
- 네트워크는 주입형 http_get으로 추상화 → 단위 테스트 네트워크 0.
- numeric/series(ECOS/EIA/KMA)는 structured_signal, nyt는 article_candidate(공식 API 기사 메타).

stdlib + httpx(기존). 신규 설치 0.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

from ingestion.core.env_loader import load_env
from ingestion.orchestration.full_source_revival import build_eventqueue_record

# http_get(url, params) -> (status_code, json_obj|None, text|None)
HttpGet = Callable[..., "tuple[Optional[int], Optional[dict], Optional[str]]"]
# http_post(url, *, json, headers_policy) -> (status_code, json_obj|None, text|None)
HttpPost = Callable[..., "tuple[Optional[int], Optional[dict], Optional[str]]"]


@dataclass(frozen=True)
class VendorRouteResult:
    source_id: str
    route_name: str
    success: bool
    status_code: Optional[int]
    record_type: str
    records: tuple[dict, ...]
    error: Optional[str]
    item_count: int


def _resolve_key(*names: str, env: Optional[dict] = None) -> Optional[str]:
    """env에서 키 값을 읽는다(존재 시 반환, 절대 로깅 안 함). alias도 시도."""
    env = env if env is not None else load_env()
    for n in names:
        v = os.environ.get(n) or env.get(n)
        if v:
            return v
    return None


def _default_http_get(url, params=None):
    """httpx GET. (status, json|None, text|None). 신규 설치 0."""
    import httpx
    r = httpx.get(url, params=params, timeout=20.0)
    ct = (r.headers.get("content-type") or "").lower()
    j = None
    if "json" in ct:
        try:
            j = r.json()
        except Exception:
            j = None
    return r.status_code, j, (None if j is not None else r.text)


def _ref_url(base: str, params: dict, *, drop: tuple[str, ...]) -> str:
    """key 등 secret param을 제거한 안정 참조 URL(evidence). 결정적(정렬)."""
    safe = {k: v for k, v in params.items() if k not in drop}
    q = urlencode(sorted(safe.items()))
    return f"{base}?{q}" if q else base


# ── bok_ecos: ECOS StatisticSearch ───────────────────────────────────────────
# 기본 통계: 722Y001(한국은행 기준금리), cycle M, item 0101000. (운영 시 source별 확장)
_ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
_ECOS_STAT = "722Y001"
_ECOS_CYCLE = "M"
_ECOS_ITEM = "0101000"


def fetch_bok_ecos(*, env=None, http_get: HttpGet = _default_http_get,
                   now: Optional[datetime] = None, limit: int = 5) -> VendorRouteResult:
    key = _resolve_key("BOK_ECOS_API_KEY", "ECOS_API_KEY", env=env)
    if not key:
        return VendorRouteResult("bok_ecos", "ecos_statistic_search", False, None,
                                 "structured_signal", (), "key_missing", 0)
    now = now or datetime.now(timezone.utc)
    start = (now.year - 1) * 100 + 1   # 작년 1월부터
    end = now.year * 100 + now.month
    url = f"{_ECOS_BASE}/{key}/json/kr/1/{limit}/{_ECOS_STAT}/{_ECOS_CYCLE}/{start:06d}/{end:06d}/{_ECOS_ITEM}"
    # evidence는 key 제거한 경로
    ref = (f"{_ECOS_BASE}/json/kr/1/{limit}/{_ECOS_STAT}/{_ECOS_CYCLE}/{start:06d}/{end:06d}/{_ECOS_ITEM}")
    try:
        status, j, _ = http_get(url)
    except Exception as exc:
        return VendorRouteResult("bok_ecos", "ecos_statistic_search", False, None,
                                 "structured_signal", (), f"fetch_error:{type(exc).__name__}", 0)
    rows = ((j or {}).get("StatisticSearch", {}) or {}).get("row", []) if j else []
    if status != 200 or not rows:
        err = ((j or {}).get("RESULT", {}) or {}).get("MESSAGE") if j else f"http_{status}"
        return VendorRouteResult("bok_ecos", "ecos_statistic_search", False, status,
                                 "structured_signal", (), err or "no_rows", 0)
    records = []
    for r in rows:
        time_raw = r.get("TIME")
        observed = _ecos_time_to_iso(time_raw)
        label = " ".join(x for x in (r.get("STAT_NAME"), r.get("ITEM_NAME1")) if x)
        unit = r.get("UNIT_NAME") or ""
        records.append(build_eventqueue_record(
            record_type="structured_signal", source_id="bok_ecos",
            title_or_label=f"{label} = {r.get('DATA_VALUE')} {unit}".strip(),
            source_url_or_evidence=ref, canonical_url=f"{ref}#t={time_raw}",
            published_at_or_observed_at=observed, body_state_or_signal="economic_indicator",
            confirmation_policy="evidence_required", quality_pre_gate_decision="pass",
        ))
    return VendorRouteResult("bok_ecos", "ecos_statistic_search", True, status,
                             "structured_signal", tuple(records), None, len(records))


def _ecos_time_to_iso(t: Optional[str]) -> Optional[str]:
    if not t:
        return None
    t = str(t)
    if len(t) == 6:   # YYYYMM
        return f"{t[:4]}-{t[4:6]}"
    if len(t) == 8:   # YYYYMMDD
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    if len(t) == 4:   # YYYY
        return t
    return t


# ── eia: EIA v2 data ─────────────────────────────────────────────────────────
_EIA_BASE = "https://api.eia.gov/v2/natural-gas/pri/sum/data/"


def fetch_eia(*, env=None, http_get: HttpGet = _default_http_get,
              now: Optional[datetime] = None, limit: int = 5) -> VendorRouteResult:
    key = _resolve_key("EIA_API_KEY", env=env)
    if not key:
        return VendorRouteResult("eia", "eia_v2_data", False, None,
                                 "structured_signal", (), "key_missing", 0)
    params = {
        "api_key": key, "frequency": "monthly", "data[0]": "value",
        "sort[0][column]": "period", "sort[0][direction]": "desc", "length": str(limit),
    }
    ref = _ref_url(_EIA_BASE, params, drop=("api_key",))
    try:
        status, j, _ = http_get(_EIA_BASE, params)
    except Exception as exc:
        return VendorRouteResult("eia", "eia_v2_data", False, None,
                                 "structured_signal", (), f"fetch_error:{type(exc).__name__}", 0)
    data = ((j or {}).get("response", {}) or {}).get("data", []) if j else []
    if status != 200 or not data:
        return VendorRouteResult("eia", "eia_v2_data", False, status,
                                 "structured_signal", (), f"http_{status}_no_data", 0)
    records = []
    for d in data:
        period = d.get("period")
        records.append(build_eventqueue_record(
            record_type="structured_signal", source_id="eia",
            title_or_label=f"{d.get('series-description') or d.get('area-name')}: {d.get('value')} {d.get('units') or ''}".strip(),
            source_url_or_evidence=ref, canonical_url=f"{ref}#series={d.get('series')}&t={period}",
            published_at_or_observed_at=str(period) if period else None,
            body_state_or_signal="energy_price",
            confirmation_policy="evidence_required", quality_pre_gate_decision="pass",
        ))
    return VendorRouteResult("eia", "eia_v2_data", True, status,
                             "structured_signal", tuple(records), None, len(records))


# ── kma: getUltraSrtNcst (초단기실황) ─────────────────────────────────────────
_KMA_BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"


def _kma_base_slot(now: Optional[datetime] = None) -> tuple[str, str]:
    """KST 기준 직전 정시 슬롯(관측 발표 지연 고려, -1h HH00)."""
    now = now or datetime.now(timezone.utc)
    kst = now.astimezone(timezone.utc) + timedelta(hours=9)
    base = kst - timedelta(hours=1)
    return base.strftime("%Y%m%d"), base.strftime("%H00")


def fetch_kma(*, env=None, http_get: HttpGet = _default_http_get,
              now: Optional[datetime] = None, nx: int = 60, ny: int = 127) -> VendorRouteResult:
    key = _resolve_key("KMA_API_KEY", env=env)
    if not key:
        return VendorRouteResult("kma", "kma_ultra_srt_ncst", False, None,
                                 "structured_signal", (), "key_missing", 0)
    bd, bt = _kma_base_slot(now)
    params = {"serviceKey": key, "dataType": "JSON", "numOfRows": "20", "pageNo": "1",
              "base_date": bd, "base_time": bt, "nx": str(nx), "ny": str(ny)}
    ref = _ref_url(_KMA_BASE, params, drop=("serviceKey",))
    try:
        status, j, _ = http_get(_KMA_BASE, params)
    except Exception as exc:
        return VendorRouteResult("kma", "kma_ultra_srt_ncst", False, None,
                                 "structured_signal", (), f"fetch_error:{type(exc).__name__}", 0)
    header = ((j or {}).get("response", {}) or {}).get("header", {}) if j else {}
    result_code = header.get("resultCode")
    if status != 200 or result_code not in ("00", 0):
        return VendorRouteResult("kma", "kma_ultra_srt_ncst", False, status,
                                 "structured_signal", (),
                                 f"result_code_{result_code}:{header.get('resultMsg')}", 0)
    items = (((j or {}).get("response", {}) or {}).get("body", {}) or {}).get("items", {}) or {}
    item_list = items.get("item", []) if isinstance(items, dict) else []
    observed = f"{bd[:4]}-{bd[4:6]}-{bd[6:8]}T{bt[:2]}:00:00+09:00"
    records = []
    for it in item_list:
        cat = it.get("category")
        records.append(build_eventqueue_record(
            record_type="structured_signal", source_id="kma",
            title_or_label=f"KMA 실황 {cat}={it.get('obsrValue')} (nx={it.get('nx')},ny={it.get('ny')})",
            source_url_or_evidence=ref,
            canonical_url=f"{ref}#cat={cat}&t={bd}{bt}",
            published_at_or_observed_at=observed, body_state_or_signal="weather_observation",
            confirmation_policy="source_confirmed", quality_pre_gate_decision="pass",
        ))
    if not records:
        return VendorRouteResult("kma", "kma_ultra_srt_ncst", False, status,
                                 "structured_signal", (), "no_items", 0)
    return VendorRouteResult("kma", "kma_ultra_srt_ncst", True, status,
                             "structured_signal", tuple(records), None, len(records))


# ── nyt: Article Search API (공식 API, 우회 아님) ─────────────────────────────
_NYT_BASE = "https://api.nytimes.com/svc/search/v2/articlesearch.json"


def fetch_nyt(*, env=None, http_get: HttpGet = _default_http_get,
              query: str = "technology", limit: int = 10) -> VendorRouteResult:
    key = _resolve_key("NYT_API_KEY", env=env)
    if not key:
        return VendorRouteResult("nyt", "nyt_article_search", False, None,
                                 "article_candidate", (), "key_missing", 0)
    params = {"q": query, "api-key": key, "sort": "newest"}
    try:
        status, j, _ = http_get(_NYT_BASE, params)
    except Exception as exc:
        return VendorRouteResult("nyt", "nyt_article_search", False, None,
                                 "article_candidate", (), f"fetch_error:{type(exc).__name__}", 0)
    docs = (((j or {}).get("response", {}) or {}).get("docs", [])) if j else []
    if status != 200 or not docs:
        return VendorRouteResult("nyt", "nyt_article_search", False, status,
                                 "article_candidate", (), f"http_{status}_no_docs", 0)
    records = []
    for d in docs[:limit]:
        headline = (d.get("headline") or {}).get("main") if isinstance(d.get("headline"), dict) else d.get("headline")
        web_url = d.get("web_url")
        if not web_url:
            continue  # 외부 URL 없으면 스킵(둔갑 금지)
        records.append(build_eventqueue_record(
            record_type="article_candidate", source_id="nyt",
            title_or_label=headline, source_url_or_evidence=web_url,
            canonical_url=web_url, published_at_or_observed_at=d.get("pub_date"),
            # 공식 API는 abstract/snippet(요약)만 제공 → 본문 전문 아님(정직히 snippet_only)
            body_state_or_signal="snippet_only",
            confirmation_policy="source_confirmed", quality_pre_gate_decision="pass",
        ))
    if not records:
        return VendorRouteResult("nyt", "nyt_article_search", False, status,
                                 "article_candidate", (), "no_url_docs", 0)
    return VendorRouteResult("nyt", "nyt_article_search", True, status,
                             "article_candidate", tuple(records), None, len(records))


# ── gdelt: DOC 2.0 ArtList (키 불필요, 좁은 쿼리 단발로 제공자 한도 존중) ─────────
_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_gdelt(*, env=None, http_get: HttpGet = _default_http_get,
                query: str = "climate OR economy OR election", limit: int = 5,
                timespan: str = "1d") -> VendorRouteResult:
    """GDELT DOC ArtList. 429(rate-limit) note면 우회하지 않고 실패로 보고(무한 retry 금지)."""
    params = {"query": query, "mode": "ArtList", "maxrecords": str(limit),
              "format": "json", "timespan": timespan}
    ref = _ref_url(_GDELT_BASE, params, drop=())
    try:
        status, j, text = http_get(_GDELT_BASE, params)
    except Exception as exc:
        return VendorRouteResult("gdelt", "gdelt_doc_artlist", False, None,
                                 "official_record", (), f"fetch_error:{type(exc).__name__}", 0)
    if status == 429 or (j is None and text and "limit requests" in text.lower()):
        return VendorRouteResult("gdelt", "gdelt_doc_artlist", False, status or 429,
                                 "official_record", (), "provider_rate_limited", 0)
    arts = (j or {}).get("articles", []) if j else []
    if status != 200 or not arts:
        return VendorRouteResult("gdelt", "gdelt_doc_artlist", False, status,
                                 "official_record", (), f"http_{status}_no_articles", 0)
    records = []
    for a in arts:
        url = a.get("url")
        if not url:
            continue
        records.append(build_eventqueue_record(
            record_type="official_record", source_id="gdelt", title_or_label=a.get("title"),
            source_url_or_evidence=url, canonical_url=url,
            published_at_or_observed_at=a.get("seendate"), body_state_or_signal="official_record",
            confirmation_policy="evidence_required", quality_pre_gate_decision="pass",
        ))
    if not records:
        return VendorRouteResult("gdelt", "gdelt_doc_artlist", False, status,
                                 "official_record", (), "no_url_articles", 0)
    return VendorRouteResult("gdelt", "gdelt_doc_artlist", True, status,
                             "official_record", tuple(records), None, len(records))


# ── product_hunt: GraphQL(공식 API, bearer). 실 url/createdAt 확보(합성 제거) ──────
_PH_ENDPOINT = "https://api.producthunt.com/v2/api/graphql"
_PH_QUERY = ("{ posts(first: %d) { edges { node { id name tagline slug url "
             "createdAt featuredAt votesCount } } } }")


def _default_http_post(url, *, json_body=None, bearer=None):
    """httpx POST(JSON). (status, json|None, text|None). bearer는 호출 시점에만 헤더로 사용."""
    import httpx
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    r = httpx.post(url, json=json_body, headers=headers, timeout=25.0)
    try:
        return r.status_code, r.json(), None
    except Exception:
        return r.status_code, None, r.text


def _canonical_ph_url(url: Optional[str]) -> Optional[str]:
    """utm 등 추적 쿼리를 제거한 안정 product URL(외부 식별 + 재현 가능)."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def fetch_product_hunt(*, env=None, http_post: HttpPost = None, limit: int = 5) -> VendorRouteResult:
    """Product Hunt GraphQL — 확장 쿼리로 실 url/createdAt 확보. 합성 slug 사용 안 함.

    bearer token은 env_loader로만 읽고 요청 헤더에만 사용(로그/직렬화 금지). url의 추적 쿼리는
    canonical에서 제거. url 없는 노드는 스킵(둔갑 금지).
    """
    tok = _resolve_key("PRODUCT_HUNT_ACCESS_TOKEN", "PRODUCT_HUNT_API_KEY", env=env)
    if not tok:
        return VendorRouteResult("product_hunt", "ph_graphql_posts", False, None,
                                 "community_signal", (), "key_missing", 0)
    post = http_post or (lambda url, **kw: _default_http_post(url, **kw))
    body = {"query": _PH_QUERY % max(1, int(limit))}
    try:
        status, j, text = post(_PH_ENDPOINT, json_body=body, bearer=tok)
    except Exception as exc:
        return VendorRouteResult("product_hunt", "ph_graphql_posts", False, None,
                                 "community_signal", (), f"fetch_error:{type(exc).__name__}", 0)
    if status == 429:
        return VendorRouteResult("product_hunt", "ph_graphql_posts", False, 429,
                                 "community_signal", (), "provider_rate_limited", 0)
    edges = ((((j or {}).get("data") or {}).get("posts") or {}).get("edges")) if j else None
    if status != 200 or not edges:
        err = "graphql_errors" if (j and j.get("errors")) else f"http_{status}_no_edges"
        return VendorRouteResult("product_hunt", "ph_graphql_posts", False, status,
                                 "community_signal", (), err, 0)
    records = []
    for e in edges:
        node = e.get("node") if isinstance(e, dict) else None
        if not isinstance(node, dict):
            continue
        canon = _canonical_ph_url(node.get("url"))
        created = node.get("createdAt") or node.get("featuredAt")
        if not canon or not created:
            continue   # 실 url/시간 없으면 스킵(합성/둔갑 금지)
        records.append(build_eventqueue_record(
            record_type="community_signal", source_id="product_hunt",
            title_or_label=node.get("name"), source_url_or_evidence=canon, canonical_url=canon,
            published_at_or_observed_at=created, body_state_or_signal="community_signal",
            confirmation_policy="unconfirmed_until_corroborated", quality_pre_gate_decision="pass",
        ))
    if not records:
        return VendorRouteResult("product_hunt", "ph_graphql_posts", False, status,
                                 "community_signal", (), "no_real_url_or_date", 0)
    return VendorRouteResult("product_hunt", "ph_graphql_posts", True, status,
                             "community_signal", tuple(records), None, len(records))


# ── culture_info: data.go.kr period2(list) → detail2(seq→실 url) ──────────────
_CULTURE_LIST = "https://apis.data.go.kr/B553457/cultureinfo/period2"
_CULTURE_DETAIL = "https://apis.data.go.kr/B553457/cultureinfo/detail2"


def _culture_date_iso(d: Optional[str]) -> Optional[str]:
    """YYYYMMDD → YYYY-MM-DD. 형식 외면 원본 유지."""
    if d and len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d or None


def fetch_culture_info(*, env=None, http_get: HttpGet = None, limit: int = 5,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       now: Optional[datetime] = None) -> VendorRouteResult:
    """문화포털 공식 open API. list(period2)로 seq 확보 후 detail2로 실 외부 url 매핑.

    detail2가 주는 실 url(전시/공연 공식 페이지)을 사용 — culture.go.kr 합성 detailView 죽은
    shell을 쓰지 않는다. url 없는 항목은 스킵. serviceKey는 env로만 읽고 evidence URL에서 제거.
    """
    key = _resolve_key("CULTURE_INFO_API_KEY", "CULTURE_INFO_KEY", env=env)
    if not key:
        return VendorRouteResult("culture_info", "culture_period2_detail2", False, None,
                                 "official_record", (), "key_missing", 0)
    get = http_get or (lambda url, params=None: _culture_xml_get(url, params))
    now = now or datetime.now(timezone.utc)
    frm = from_date or (now - timedelta(days=3)).strftime("%Y%m%d")
    to = to_date or (now + timedelta(days=40)).strftime("%Y%m%d")
    list_params = {"serviceKey": key, "from": frm, "to": to, "rows": str(limit), "cPage": "1"}
    try:
        status, _, text = get(_CULTURE_LIST, list_params)
    except Exception as exc:
        return VendorRouteResult("culture_info", "culture_period2_detail2", False, None,
                                 "official_record", (), f"fetch_error:{type(exc).__name__}", 0)
    seqs = _culture_parse_list(text)
    if status != 200 or not seqs:
        return VendorRouteResult("culture_info", "culture_period2_detail2", False, status,
                                 "official_record", (), f"http_{status}_no_items", 0)
    records = []
    for seq in seqs[:limit]:
        try:
            dstatus, _, dtext = get(_CULTURE_DETAIL, {"serviceKey": key, "seq": seq})
        except Exception:
            continue
        if dstatus != 200 or not dtext:
            continue
        item = _culture_parse_detail(dtext)
        if not item:
            continue
        url = item.get("url")
        if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
            continue   # 실 외부 url 없으면 스킵(합성 금지)
        start = _culture_date_iso(item.get("startDate"))
        records.append(build_eventqueue_record(
            record_type="official_record", source_id="culture_info",
            title_or_label=item.get("title"), source_url_or_evidence=url,
            canonical_url=f"{url}#seq={seq}", published_at_or_observed_at=start,
            body_state_or_signal="official_record",
            confirmation_policy="source_confirmed", quality_pre_gate_decision="pass",
        ))
    if not records:
        return VendorRouteResult("culture_info", "culture_period2_detail2", False, status,
                                 "official_record", (), "no_detail_url", 0)
    return VendorRouteResult("culture_info", "culture_period2_detail2", True, status,
                             "official_record", tuple(records), None, len(records))


def _culture_xml_get(url, params=None):
    """httpx GET, XML은 text로 반환. (status, None, text)."""
    import httpx
    r = httpx.get(url, params=params, timeout=20.0)
    return r.status_code, None, r.text


def _culture_parse_list(text: Optional[str]) -> list[str]:
    """period2 XML → seq 목록."""
    if not text:
        return []
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(text)
    except Exception:
        return []
    out = []
    for it in (root.findall(".//items/item") or root.findall(".//item")):
        seq = it.findtext("seq") or it.findtext("serviceId")
        if seq:
            out.append(seq.strip())
    return out


def _culture_parse_detail(text: Optional[str]) -> Optional[dict]:
    """detail2 XML → {title,startDate,url,place} (첫 item)."""
    if not text:
        return None
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(text)
    except Exception:
        return None
    it = root.find(".//items/item") or root.find(".//item")
    if it is None:
        return None
    # 적대 리뷰 흡수(HIGH-3): placeUrl(장소 홈페이지) 폴백 금지 — 전시/공연 고유 url이 없으면
    # 무관한 venue 홈을 evidence로 둔갑시키지 않고 None(상위에서 스킵). 고유 url만 stable evidence.
    return {
        "title": it.findtext("title"), "startDate": it.findtext("startDate"),
        "endDate": it.findtext("endDate"), "place": it.findtext("place"),
        "url": (it.findtext("url") or "").strip() or None,
    }


# ── dispatch ─────────────────────────────────────────────────────────────────
VENDOR_ROUTES: dict[str, Callable[..., VendorRouteResult]] = {
    "bok_ecos": fetch_bok_ecos,
    "eia": fetch_eia,
    "kma": fetch_kma,
    "nyt": fetch_nyt,
    "gdelt": fetch_gdelt,
    "product_hunt": fetch_product_hunt,
    "culture_info": fetch_culture_info,
}


def has_vendor_route(source_id: str) -> bool:
    return source_id in VENDOR_ROUTES


def fetch_vendor(source_id: str, **kwargs) -> Optional[VendorRouteResult]:
    fn = VENDOR_ROUTES.get(source_id)
    if fn is None:
        return None
    return fn(**kwargs)
