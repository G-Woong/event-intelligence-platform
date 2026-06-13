from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ingestion.core.artifact_store import (
    new_run_id,
    save_extracted_payload,
    save_raw_payload,
    url_hash,
)
from ingestion.core.env_loader import _ALIASES, env_status, load_env
from ingestion.probes.models import ProbeResult
from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS

logger = logging.getLogger("ingestion.probes.api_probe")

_HONEST_UA = "event-intelligence/0.7 (+ei)"
_TIMEOUT_SEC = 20.0

# In-memory Twitch OAuth token cache for IGDB (never persisted)
_igdb_token_cache: dict = {"token": None, "expires_at": 0.0}


def _igdb_get_access_token(client_id: str, client_secret: str) -> Optional[str]:
    """Exchange Twitch client_credentials for IGDB access token. Memory-cached."""
    import time
    import httpx as _httpx

    cached = _igdb_token_cache
    if cached["token"] and time.monotonic() < cached["expires_at"] - 60:
        return cached["token"]  # type: ignore[return-value]

    try:
        resp = _httpx.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))
        if token:
            cached["token"] = token
            cached["expires_at"] = time.monotonic() + expires_in
        return token
    except Exception:
        return None

# Per-service probe specs: extra params and meaningful response fields
_PROBE_SPEC: dict[str, dict] = {
    "naver_news_search": {
        "extra_params": {"query": "테스트", "display": "3"},
        "meaningful_fields": ["items"],
        "response_format": "json",
        "query_param": "query",
    },
    "naver_blog_search": {
        "extra_params": {"query": "테스트", "display": "3"},
        "meaningful_fields": ["items"],
        "response_format": "json",
        "query_param": "query",
    },
    "youtube": {
        "extra_params": {"part": "snippet", "q": "samsung", "maxResults": "3", "type": "video"},
        "meaningful_fields": ["items", "pageInfo"],
        "response_format": "json",
        "query_param": "q",
    },
    "opendart": {
        "extra_params": {"bgn_de": "20260529", "end_de": "20260603", "page_count": "3"},
        "meaningful_fields": ["list", "total_count"],
        "response_format": "json",
    },
    "eia": {
        "extra_params": {},
        "meaningful_fields": ["response.routes"],
        "response_format": "json",
    },
    "product_hunt": {
        "extra_params": {},
        "meaningful_fields": ["data.posts.edges"],
        "response_format": "json",
        "method": "POST",
        "json_body": {"query": "{ posts(first: 3) { edges { node { name tagline } } } }"},
    },
    "gdelt": {
        "extra_params": {"query": "samsung", "mode": "artlist", "format": "json", "maxrecords": "3"},
        "meaningful_fields": ["articles"],
        "response_format": "json",
        "query_param": "query",
        "query_transform": "quote_phrase",
    },
    "sec_edgar": {
        "extra_params": {"q": "samsung", "dateRange": "custom", "startdt": "2026-01-01", "enddt": "2026-06-03"},
        "meaningful_fields": ["hits.hits"],
        "response_format": "json",
        "query_param": "q",
    },
    "federal_register": {
        # fields[]를 title만 받던 것이 partial의 원인 (docs/88). httpx는 list 값을
        # 같은 키 반복으로 직렬화한다 (fields[]=title&fields[]=html_url&...).
        "extra_params": {
            "per_page": "3",
            "order": "newest",
            "fields[]": ["title", "html_url", "publication_date", "abstract", "document_number"],
        },
        "meaningful_fields": ["results", "count"],
        "response_format": "json",
        "query_param": "conditions[term]",
    },
    "hacker_news": {
        # topstories.json은 정수 id 배열만 반환 — title/url은 /v0/item/{id}.json 2차 호출.
        "extra_params": {},
        "meaningful_fields": [],
        "response_format": "json",
        "detail_endpoint_template": "https://hacker-news.firebaseio.com/v0/item/{id}.json",
        "detail_limit": 3,
    },
    "bok_ecos": {
        "extra_params": {},
        "meaningful_fields": ["StatisticTableList.row"],
        "response_format": "json",
        "key_in_url": True,
    },
    "reddit": {
        "extra_params": {},
        "meaningful_fields": ["data"],
        "response_format": "json",
    },
    "coinbase_market": {
        "extra_params": {},
        "meaningful_fields": ["products"],
        "response_format": "json",
    },
    "binance_market": {
        "extra_params": {},
        "meaningful_fields": [],
        "response_format": "json",
    },
    # RSS / XML sources (connectivity check only)
    "bbc": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml"},
    # ap_news: Google News RSS 프록시. query는 params로 전달(endpoint에 박으면 httpx가 빈 params로 덮어써 404).
    "ap_news": {"extra_params": {"q": "site:apnews.com", "hl": "en-US", "gl": "US", "ceid": "US:en"},
                "meaningful_fields": [], "response_format": "xml"},
    "techcrunch": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml"},
    "the_verge": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml"},
    "yna": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml"},
    "hankyung": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml"},
    "maekyung": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml"},
    "aljazeera": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml"},
    "cnbc": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml"},
    # HTML-only sources
    "zdnet_korea": {"extra_params": {}, "meaningful_fields": [], "response_format": "html"},
    "etnews": {"extra_params": {}, "meaningful_fields": [], "response_format": "html"},
    "dcinside": {"extra_params": {}, "meaningful_fields": [], "response_format": "html"},
    "fmkorea": {"extra_params": {}, "meaningful_fields": [], "response_format": "html"},
    # XML API sources
    "kopis": {
        "extra_params": {"stdate": "20260529", "eddate": "20260603", "cpage": "1", "rows": "3"},
        "meaningful_fields": [],
        "response_format": "xml",
    },
    "aladin": {
        "extra_params": {
            "QueryType": "Bestseller", "MaxResults": "3", "start": "1",
            "SearchTarget": "Book", "output": "js", "Version": "20131101",
        },
        "meaningful_fields": ["item"],
        "response_format": "json",
    },
    # Search/AI sources (POST, key required)
    "serper": {
        "extra_params": {},
        "meaningful_fields": ["organic"],
        "response_format": "json",
        "method": "POST",
        "json_body": {"q": "breaking news", "num": 3},
        "query_param": "q",
        "query_in": "json_body",
    },
    "tavily": {
        "extra_params": {},
        "meaningful_fields": ["results"],
        "response_format": "json",
        "method": "POST",
        "json_body": {"query": "breaking news", "search_depth": "basic", "max_results": 3},
        "query_param": "query",
        "query_in": "json_body",
    },
    "exa": {
        "extra_params": {},
        "meaningful_fields": ["results"],
        "response_format": "json",
        "method": "POST",
        "json_body": {"query": "breaking news", "numResults": 3},
        "query_param": "query",
        "query_in": "json_body",
    },
    "newsapi": {
        # /v2/everything: q 필수, country 미지원(400). 기본 q는 연결성 체크용.
        "extra_params": {"q": "news", "pageSize": "3", "sortBy": "publishedAt", "language": "en"},
        "meaningful_fields": ["articles"],
        "response_format": "json",
        "query_param": "q",
    },
    # search_enrichment: query 주입 라운드(docs/85)에서 신설 — 이전에는 default spec.
    # entry 신설로 --all-safe 및 collection_probe Route 1 거동이 바뀐다 (docs/85 §11).
    "gnews": {
        "extra_params": {"max": "3", "lang": "en"},
        "meaningful_fields": ["articles"],
        "response_format": "json",
        "query_param": "q",
    },
    "guardian": {
        "extra_params": {"page-size": "3"},
        "meaningful_fields": ["response.results"],
        "response_format": "json",
        "query_param": "q",
    },
    "nyt": {
        "extra_params": {},
        "meaningful_fields": ["response.docs"],
        "response_format": "json",
        "query_param": "q",
    },
    "culture_info": {
        # data.go.kr B553457/cultureinfo/period2 — 기간 조회 (XML)
        "extra_params": {"from": "20260610", "to": "20260620", "rows": "3", "cPage": "1"},
        "meaningful_fields": [],
        "response_format": "xml",
    },
    "twelve_data": {
        "extra_params": {"symbol": "AAPL", "interval": "1day", "outputsize": "3"},
        "meaningful_fields": ["values"],
        "response_format": "json",
    },
    "kma": {
        # data.go.kr 단기예보 초단기실황 — base_date/base_time + 격자(nx,ny: 서울)
        "extra_params": {
            "pageNo": "1", "numOfRows": "10", "dataType": "JSON",
            "base_date": "20260612", "base_time": "0600",
            "nx": "60", "ny": "127",
        },
        "meaningful_fields": ["response.body.items.item"],
        "response_format": "json",
    },
    # P0: missing probe specs (added this round)
    "google_programmable_search": {
        "extra_params": {"q": "뉴스"},
        "meaningful_fields": ["items"],
        "response_format": "json",
    },
    "finnhub": {
        "extra_params": {"symbol": "AAPL"},
        "meaningful_fields": ["c", "h", "l", "o", "pc"],
        "response_format": "json",
    },
    "kofic": {
        # targetDt: most recent business day from 2026-06-03
        "extra_params": {"targetDt": "20260602"},
        "meaningful_fields": ["boxOfficeResult.dailyBoxOfficeList"],
        "response_format": "json",
    },
    "alpha_vantage": {
        "extra_params": {
            "function": "TIME_SERIES_DAILY",
            "symbol": "AAPL",
            "outputsize": "compact",
        },
        "meaningful_fields": ["Time Series (Daily)"],
        "response_format": "json",
    },
    "igdb": {
        "extra_params": {},
        "meaningful_fields": [],
        "response_format": "json",
        "method": "POST",
        "apicalypse_body": "fields name,url,first_release_date,rating; where rating > 80; limit 3;",
    },
    # P2: Korean public API specs (added this round)
    "tour": {
        # KorService2/areaBasedList2 — same param contract as KorService1
        "extra_params": {
            "MobileOS": "ETC",
            "MobileApp": "EventIntelligence",
            "_type": "json",
            "numOfRows": "3",
            "pageNo": "1",
            "areaCode": "1",
        },
        "meaningful_fields": ["response.body.items.item"],
        "response_format": "json",
    },
    "its": {
        # /trafficInfo — bbox(서울 도심) + getType=json; type: all|ex|its
        "extra_params": {
            "type": "all",
            "minX": "126.8", "maxX": "127.2",
            "minY": "37.4", "maxY": "37.7",
            "getType": "json",
        },
        "meaningful_fields": ["body.items"],
        "response_format": "json",
    },
    # domain_signal: query 주입 라운드(docs/85)에서 신설.
    # 기본 endpoint(/movie/popular)는 query 미지원 — query 시 /search/movie로 전환.
    "tmdb": {
        "extra_params": {"page": "1"},
        "meaningful_fields": ["results"],
        "response_format": "json",
        "query_param": "query",
        "query_endpoint": "https://api.themoviedb.org/3/search/movie",
    },
}

_NEXT_ACTION_MAP: dict[str, str] = {
    "LIVE_SUCCESS": "integrate_into_pipeline",
    "LIVE_PARTIAL": "check_selector_or_endpoint",
    "MISSING_KEY": "add_key_to_.env",
    "INVALID_KEY": "rotate_key",
    "PERMISSION_DENIED": "check_plan_scope",
    "RATE_LIMITED": "retry_after_cooldown:300s",
    "QUOTA_EXHAUSTED": "wait_quota_reset",
    "PLAN_RESTRICTED": "upgrade_plan",
    "ENDPOINT_DEPRECATED": "update_endpoint",
    "PARSE_ERROR": "inspect_raw_payload",
    "NETWORK_ERROR": "check_connectivity",
    "TIMEOUT": "retry_later",
    "SCHEMA_CHANGED": "update_probe_spec",
    "UNKNOWN": "inspect_raw_payload",
    "BLOCKED": "see_compliance_boundary",
    "DEFERRED": "schedule_next_round",
    # New classifications
    "QUERY_ENCODING_OR_PARAM_ERROR": "fix_query_encoding_or_add_required_params",
    "INVALID_SYMBOL_OR_EMPTY_MARKET_DATA": "fix_symbol_or_check_market_data_access",
    "XML_PARAMETER_ERROR": "fix_xml_request_parameters",
    "API_RETURNED_HTML_ERROR_PAGE": "inspect_raw_payload_for_html_error",
    "PARAMETER_MISSING": "add_required_params_to_probe_spec",
    "ENDPOINT_INVALID": "verify_endpoint_url",
    "DYNAMIC_RENDER_REQUIRED": "use_playwright_probe",
    "IGDB_OAUTH_FAILED": "check_igdb_client_credentials",
}


def _resolve_key(key: str) -> Optional[str]:
    """Read env key with alias support. Value is never logged."""
    val = os.environ.get(key)
    if val:
        return val
    for alias in _ALIASES.get(key, []):
        val = os.environ.get(alias)
        if val:
            return val
    return None


def _sanitize_response(text: str, secrets: list[str]) -> str:
    """Replace any echoed secret values in response body with ***REDACTED***."""
    for s in secrets:
        if s and len(s) > 4:
            text = text.replace(s, "***REDACTED***")
    return text


def _http_status_to_probe_status(http_status: int) -> str:
    if http_status == 401:
        return "INVALID_KEY"
    if http_status == 403:
        return "PERMISSION_DENIED"
    if http_status == 402:
        return "PLAN_RESTRICTED"
    if http_status == 429:
        return "RATE_LIMITED"
    if http_status == 410:
        return "ENDPOINT_DEPRECATED"
    if 500 <= http_status < 600:
        return "NETWORK_ERROR"
    if 200 <= http_status < 300:
        return "LIVE_SUCCESS"
    return "UNKNOWN"


def _transform_query(query: str, transform: str) -> str:
    """spec 메타 query_transform에 따른 소스별 query 전처리.

    quote_phrase: 공백 포함 다단어 query를 큰따옴표로 감싼다.
    GDELT DOC API는 따옴표 없는 다단어 구를 오류 텍스트(HTTP 200)로 응답한다 (docs/89 §5-2).
    """
    if transform == "quote_phrase":
        q = (query or "").strip().strip('"')
        if " " in q:
            return f'"{q}"'
        return q
    return query


def _apply_query_override(probe_spec: dict, query: Optional[str]) -> dict:
    """query를 probe_spec에 주입한 **새 dict**를 반환한다 (순수 함수).

    deepcopy 필수 — in-place 수정 시 모듈 전역 _PROBE_SPEC이 오염되어
    배치 루프에서 이전 query가 잔류한다. query_param 메타가 없으면 원본 반환.
    """
    if not query:
        return probe_spec
    query_param = probe_spec.get("query_param")
    if not query_param:
        return probe_spec
    import copy
    spec = copy.deepcopy(probe_spec)
    transform = spec.get("query_transform", "")
    if transform:
        query = _transform_query(query, transform)
    if spec.get("query_in", "params") == "json_body":
        body = spec.get("json_body")
        if not isinstance(body, dict):
            body = {}
        body[query_param] = query
        spec["json_body"] = body
    else:
        params = spec.get("extra_params")
        if not isinstance(params, dict):
            params = {}
        params[query_param] = query
        spec["extra_params"] = params
    return spec


def _build_request(service_id: str, config: dict, probe_spec: dict) -> tuple:
    """Build (method, url, params, headers, json_body, used_secrets).

    used_secrets holds key values in memory so response body can be sanitized
    before saving. Values are never logged.
    Raises ValueError('MISSING_KEY') if key absent, ValueError('BLOCKED') if login_required.
    """
    url: str = config["endpoint"]
    params: dict = dict(probe_spec.get("extra_params", {}))
    _ua = os.environ.get("SEC_USER_AGENT", _HONEST_UA) if service_id == "sec_edgar" else _HONEST_UA
    headers: dict = {
        "User-Agent": _ua,
        "Accept": "application/json, text/xml, */*",
    }
    json_body = probe_spec.get("json_body")
    method: str = probe_spec.get("method", "POST" if json_body else "GET")
    used_secrets: list[str] = []

    auth: str = config.get("auth", "none")
    keys: list = config.get("keys", [])

    if auth in ("none", "none_public_html") or not keys:
        pass

    elif auth == "header_x_naver":
        id_key = keys[0] if len(keys) > 0 else "NAVER_CLIENT_ID"
        sec_key = keys[1] if len(keys) > 1 else "NAVER_CLIENT_SECRET"
        client_id = _resolve_key(id_key)
        client_secret = _resolve_key(sec_key)
        if not client_id or not client_secret:
            raise ValueError("MISSING_KEY")
        headers["X-Naver-Client-Id"] = client_id
        headers["X-Naver-Client-Secret"] = client_secret
        used_secrets.extend([client_id, client_secret])

    elif auth == "header_x_api_key":
        api_key = _resolve_key(keys[0]) if keys else None
        if not api_key:
            raise ValueError("MISSING_KEY")
        headers["X-API-KEY"] = api_key
        used_secrets.append(api_key)

    elif auth == "bearer_token":
        token = _resolve_key(keys[0]) if keys else None
        if not token:
            raise ValueError("MISSING_KEY")
        headers["Authorization"] = f"Bearer {token}"
        used_secrets.append(token)

    elif auth == "igdb_client_credentials":
        client_id = _resolve_key(keys[0]) if len(keys) > 0 else None
        client_secret = _resolve_key(keys[1]) if len(keys) > 1 else None
        if not client_id or not client_secret:
            raise ValueError("MISSING_KEY")
        access_token = _igdb_get_access_token(client_id, client_secret)
        if not access_token:
            raise ValueError("IGDB_OAUTH_FAILED")
        headers["Authorization"] = f"Bearer {access_token}"
        headers["Client-ID"] = client_id
        used_secrets.extend([access_token, client_id, client_secret])

    elif auth.startswith("query_param_"):
        param_name = auth[len("query_param_"):]
        key_val = _resolve_key(keys[0]) if keys else None
        if not key_val:
            raise ValueError("MISSING_KEY")
        if probe_spec.get("key_in_url") and param_name in url:
            # Key embedded as URL path segment (e.g. BOK ECOS)
            url = url.replace(param_name, key_val)
        else:
            # serviceKey double-encoding prevention: if value contains '%', it's already
            # URL-encoded (portal Encoding key). Decode once so httpx doesn't double-encode.
            from urllib.parse import unquote
            if "%" in key_val:
                key_val = unquote(key_val)
            params[param_name] = key_val
        used_secrets.append(key_val)
        # Google CSE: inject second key (CX / Search Engine ID) as cx param
        if service_id == "google_programmable_search" and len(keys) > 1:
            cx_val = _resolve_key(keys[1])
            if not cx_val:
                raise ValueError("MISSING_KEY")
            params["cx"] = cx_val
            used_secrets.append(cx_val)

    elif auth == "login_required":
        raise ValueError("BLOCKED")

    return method, url, params, headers, json_body, used_secrets


def _count_items(parsed: dict, meaningful_fields: list[str]) -> tuple[int, list[str]]:
    """Count items found and which fields were present.

    Supports dotted paths (e.g. 'hits.hits', 'response.routes') to navigate
    nested response structures.
    """
    found_fields: list[str] = []
    max_len = 0
    for field in meaningful_fields:
        parts = field.split(".")
        val = parsed
        resolved = True
        for part in parts:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                resolved = False
                break
        if resolved:
            found_fields.append(field)
            if isinstance(val, list):
                max_len = max(max_len, len(val))
            elif isinstance(val, dict):
                max_len = max(max_len, len(val))
            elif isinstance(val, int) and val > 0:
                max_len = max(max_len, val)
            elif isinstance(val, float) and val > 0:
                # Float field (e.g. market quote) — presence signal: 1 item
                max_len = max(max_len, 1)
    if not meaningful_fields:
        max_len = len(parsed) if isinstance(parsed, dict) else 0
        found_fields = list(parsed.keys())[:5] if isinstance(parsed, dict) else []
    return max_len, found_fields


def run_api_live_probe(
    service_id: str,
    max_calls: int = 1,
    env_path: Optional[Path] = None,
    dry_run: bool = False,
    query: Optional[str] = None,
) -> ProbeResult:
    """Run one live API probe for the given service. Returns ProbeResult.

    query가 주어지고 probe spec에 query_param 메타가 있으면 검색어를 주입한다
    (_apply_query_override — 전역 스펙은 불변). 메타가 없으면 기존 거동 그대로.
    """
    if env_path:
        load_env(env_path)

    config = _SERVICE_CONFIGS.get(service_id)
    if not config:
        return ProbeResult(
            source_id=service_id,
            method="api",
            query=query,
            status="UNKNOWN",
            error_category="UNKNOWN",
            next_action="service_not_in_registry",
        )

    # Respect status_override
    override = config.get("status_override")
    if override in ("LOGIN_WALL", "LICENSE_REQUIRED"):
        return ProbeResult(
            source_id=service_id,
            method="api",
            query=query,
            status="BLOCKED",
            error_category=override,
            next_action="see_compliance_boundary",
        )
    if override == "PLAYWRIGHT_REQUIRED":
        return ProbeResult(
            source_id=service_id,
            method="api",
            query=query,
            status="DEFERRED",
            error_category="PLAYWRIGHT_REQUIRED",
            next_action="use_run_playwright_probe",
        )
    if override == "EXTERNAL_SIGNAL_SOURCE":
        return ProbeResult(
            source_id=service_id,
            method="api",
            query=query,
            status="DEFERRED",
            error_category="EXTERNAL_SIGNAL_SOURCE",
            next_action="use_run_playwright_probe",
        )

    probe_spec = _PROBE_SPEC.get(service_id, {"extra_params": {}, "meaningful_fields": [], "response_format": "json"})
    probe_spec = _apply_query_override(probe_spec, query)

    if dry_run:
        keys = config.get("keys", [])
        status_map = env_status(keys) if keys else {}
        all_present = all(v == "present" for v in status_map.values())
        if not keys:
            status = "LIVE_SUCCESS"
        elif all_present:
            status = "LIVE_SUCCESS"
        else:
            status = "MISSING_KEY"
        return ProbeResult(
            source_id=service_id,
            method="api",
            query=query,
            status=status,
            error_category="MISSING_KEY" if status == "MISSING_KEY" else None,
            next_action="run_without_dry_run",
        )

    # Build request
    try:
        method, url, params, headers, json_body, used_secrets = _build_request(service_id, config, probe_spec)
    except ValueError as exc:
        err = str(exc)
        if err == "MISSING_KEY":
            return ProbeResult(
                source_id=service_id,
                method="api",
                query=query,
                status="MISSING_KEY",
                error_category="MISSING_KEY",
                next_action="add_key_to_.env",
            )
        if err == "BLOCKED":
            return ProbeResult(
                source_id=service_id,
                method="api",
                query=query,
                status="BLOCKED",
                error_category="LOGIN_WALL",
                next_action="see_compliance_boundary",
            )
        if err == "IGDB_OAUTH_FAILED":
            return ProbeResult(
                source_id=service_id,
                method="api",
                query=query,
                status="INVALID_KEY",
                error_category="IGDB_OAUTH_FAILED",
                next_action="check_igdb_client_credentials",
            )
        return ProbeResult(
            source_id=service_id,
            method="api",
            query=query,
            status="UNKNOWN",
            error_category="UNKNOWN",
            next_action=err,
        )

    # Execute HTTP request (max 1 call enforced)
    run_id = new_run_id(0, service_id)
    uh = url_hash(config["endpoint"])  # canonical endpoint hash, no key

    # 일부 소스(tmdb)는 기본 endpoint가 query 미지원 — query 시 전용 endpoint로 전환
    if query and probe_spec.get("query_param") and probe_spec.get("query_endpoint"):
        url = probe_spec["query_endpoint"]

    try:
        import httpx
        apicalypse_body = probe_spec.get("apicalypse_body")
        with httpx.Client(timeout=_TIMEOUT_SEC, follow_redirects=True) as client:
            if method == "POST":
                if apicalypse_body:
                    post_headers = {**headers, "Content-Type": "text/plain"}
                    response = client.post(url, params=params, headers=post_headers, content=apicalypse_body)
                else:
                    response = client.post(url, params=params, headers=headers, json=json_body)
            else:
                response = client.get(url, params=params, headers=headers)
        http_status = response.status_code
        response_text = response.text
    except Exception as exc:
        err_type = "TIMEOUT" if "timeout" in type(exc).__name__.lower() else "NETWORK_ERROR"
        return ProbeResult(
            source_id=service_id,
            method="api",
            query=query,
            status=err_type,
            error_category=err_type,
            next_action=_NEXT_ACTION_MAP.get(err_type, "investigate"),
        )

    probe_status = _http_status_to_probe_status(http_status)

    # Sanitize response: some APIs echo back the API key in the response body
    response_text = _sanitize_response(response_text, used_secrets)

    # Save response body ONLY — no request headers, no URL with key params
    artifact_paths: dict = {}
    fmt = probe_spec.get("response_format", "json")
    try:
        raw_path = save_raw_payload(run_id, service_id, uh, fmt, response_text)
        artifact_paths["raw_payload"] = str(raw_path)
    except Exception as exc:
        logger.warning("raw_payload save failed for %s: %s", service_id, exc)

    # Early detection: API returned HTML error page when JSON/XML was expected
    if probe_status == "LIVE_SUCCESS" and fmt not in ("html",):
        stripped = response_text.lstrip().lower()
        if stripped.startswith("<html") or stripped.startswith("<!doctype"):
            probe_status = "API_RETURNED_HTML_ERROR_PAGE"

    # Parse and extract meaningful fields
    items_found = 0
    meaningful_found: list[str] = []
    extracted: dict = {}

    if probe_status == "LIVE_SUCCESS":
        if fmt == "json":
            try:
                parsed = response.json()
                mf = probe_spec.get("meaningful_fields", [])
                items_found, meaningful_found = _count_items(parsed, mf)
                for f in meaningful_found:
                    if f in parsed:
                        extracted[f] = parsed[f]
                if not items_found and not mf:
                    items_found = len(parsed) if isinstance(parsed, (list, dict)) else 0
                # Detect: items field empty but total is positive (query/encoding issue)
                if (
                    items_found == 0
                    and isinstance(parsed, dict)
                    and isinstance(parsed.get("total"), int)
                    and parsed.get("total", 0) > 0
                ):
                    probe_status = "QUERY_ENCODING_OR_PARAM_ERROR"
                # Detect: all meaningful fields present but all numeric zeros (invalid symbol)
                elif (
                    items_found == 0
                    and meaningful_found
                    and isinstance(parsed, dict)
                    and all(
                        isinstance(parsed.get(f), (int, float)) and parsed.get(f) == 0
                        for f in meaningful_found
                        if f in parsed
                    )
                    and all(f in parsed for f in meaningful_found)
                ):
                    probe_status = "INVALID_SYMBOL_OR_EMPTY_MARKET_DATA"
                # Detect: Alpha Vantage error message in successful 200 response
                elif isinstance(parsed, dict) and service_id == "alpha_vantage":
                    if "Error Message" in parsed:
                        probe_status = "PARAMETER_MISSING"
                        items_found = 0
                    elif "Note" in parsed or "Information" in parsed:
                        probe_status = "RATE_LIMITED"
                        items_found = 0
                elif not items_found and mf:
                    probe_status = "LIVE_PARTIAL"
            except Exception as exc:
                logger.warning("JSON parse error for %s: %s", service_id, exc)
                lower_body = response_text[:500].lower()
                if (
                    "rate limit" in lower_body
                    or "too many requests" in lower_body
                    # GDELT는 soft limit을 200+평문으로 알린다 (실측: "Please limit
                    # requests to one every 5 seconds..." — docs/89 §5-2)
                    or "limit requests" in lower_body
                ):
                    probe_status = "RATE_LIMITED"
                elif "query" in lower_body and (
                    "too short" in lower_body or "too long" in lower_body
                    or "too common" in lower_body or "invalid" in lower_body
                ):
                    # 서버가 query 형식 오류를 200+텍스트로 알린 경우 (GDELT 등)
                    probe_status = "QUERY_ENCODING_OR_PARAM_ERROR"
                else:
                    probe_status = "PARSE_ERROR"
        elif fmt == "xml":
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response_text)
                # Check for XML error response
                xml_lower = response_text.lower()
                if (
                    "invalid request" in xml_lower
                    or root.find(".//errorcode") is not None
                    or root.find(".//errormsg") is not None
                    or root.find(".//error") is not None
                ):
                    probe_status = "XML_PARAMETER_ERROR"
                    items_found = 0
                else:
                    # RSS/Atom feeds: count <item> or <entry> elements
                    items = root.findall(".//item") or root.findall(
                        ".//{http://www.w3.org/2005/Atom}entry"
                    )
                    if items:
                        items_found = len(items)
                    else:
                        items_found = len(list(root)) or (1 if len(response_text) > 100 else 0)
                    if not items_found:
                        probe_status = "LIVE_PARTIAL"
            except Exception:
                items_found = 1 if len(response_text) > 100 else 0
                if not items_found:
                    probe_status = "LIVE_PARTIAL"
        else:
            # HTML: successful response = at least some content
            items_found = 1 if len(response_text) > 100 else 0
            if not items_found:
                probe_status = "LIVE_PARTIAL"

    # detail_endpoint_template: id 목록형 응답의 상세 2차 호출 (hacker_news 등).
    # topstories.json은 정수 id 배열만 주므로 title/url을 detail에서 가져온다.
    detail_tpl = probe_spec.get("detail_endpoint_template")
    if detail_tpl and probe_status == "LIVE_SUCCESS" and fmt == "json":
        try:
            import time as _time
            import httpx as _httpx
            ids = parsed if isinstance(parsed, list) else []
            detail_items: list[dict] = []
            with _httpx.Client(timeout=_TIMEOUT_SEC) as dclient:
                for _id in ids[: int(probe_spec.get("detail_limit", 3))]:
                    r = dclient.get(detail_tpl.format(id=_id), headers=headers)
                    if r.status_code == 200:
                        d = r.json()
                        if isinstance(d, dict):
                            detail_items.append({
                                "title": d.get("title"), "url": d.get("url"),
                                "time": d.get("time"), "id": d.get("id"),
                                "score": d.get("score"),
                            })
                    _time.sleep(0.2)
            if detail_items:
                extracted["items"] = detail_items
                items_found = len(detail_items)
        except Exception as exc:
            logger.warning("detail fetch failed for %s: %s", service_id, exc)

    if extracted:
        try:
            ep = save_extracted_payload(run_id, service_id, uh, extracted)
            artifact_paths["extracted_payload"] = str(ep)
        except Exception as exc:
            logger.warning("extracted_payload save failed for %s: %s", service_id, exc)

    # RISK-T04 (docs/90 §3): Route 1 429 → cooldown 영속 기록.
    # HTTP 429와 alpha_vantage soft limit(Note/Information), 비-JSON 200 rate-limit 텍스트가
    # 모두 probe_status="RATE_LIMITED"로 수렴한다. Route 2(cloud_browser_like)와 동일한
    # record_rate_limited 경로를 써서 health gate의 should_skip / in_cooldown을 살린다.
    next_retry_at: Optional[str] = None
    if probe_status == "RATE_LIMITED":
        try:
            from ingestion.core.rate_limit_policy import (
                load_rate_limit_policy,
                record_rate_limited,
            )
            cooldown = load_rate_limit_policy(service_id).cooldown_on_429_seconds
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                cooldown = max(cooldown, int(retry_after))
            next_retry_at = record_rate_limited(
                service_id, query or "", cooldown_seconds=cooldown
            )
            logger.info(
                "RATE_LIMITED recorded for %s — next_retry=%s", service_id, next_retry_at
            )
        except Exception as exc:
            logger.warning("record_rate_limited failed for %s: %s", service_id, exc)

    return ProbeResult(
        source_id=service_id,
        method="api",
        query=query,
        status=probe_status,
        http_status=http_status,
        items_found=items_found,
        items_extracted=items_found,
        meaningful_fields=meaningful_found,
        artifact_paths=artifact_paths,
        next_retry_at=next_retry_at,
        error_category=probe_status if probe_status not in ("LIVE_SUCCESS", "LIVE_PARTIAL") else None,
        next_action=_NEXT_ACTION_MAP.get(probe_status, "investigate"),
    )
