from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ingestion.core.env_loader import env_status, load_env

# Full error taxonomy for connectivity diagnostics
CONNECTIVITY_ERROR_TAXONOMY = [
    "MISSING_KEY",
    "INVALID_KEY",
    "PERMISSION_DENIED",
    "RATE_LIMITED",
    "QUOTA_EXHAUSTED",
    "PLAN_RESTRICTED",
    "ENDPOINT_DEPRECATED",
    "DOCS_CHANGED",
    "NETWORK_ERROR",
    "TIMEOUT",
    "PARSE_ERROR",
    "SCHEMA_CHANGED",
    "LOGIN_WALL",
    "LICENSE_REQUIRED",
    "PLAYWRIGHT_REQUIRED",
    "EXTERNAL_SIGNAL_SOURCE",  # no API key; low-evidence external scrape signal
    "DEFERRED_LIVE_TEST",      # key present but live test explicitly deferred
    "UNKNOWN",
]

# Service configs: keys needed, auth method, min test endpoint, free plan summary
# auth values: none | query_param_* | header_* | bearer_token | login_required
# status_override: skips key check; used for blocked/deferred sources
_SERVICE_CONFIGS: dict[str, dict] = {
    # ── Phase 1: 기사형 뉴스 ────────────────────────────────────────────────
    "bbc": {
        "keys": [], "auth": "none",
        "endpoint": "https://feeds.bbci.co.uk/news/rss.xml",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://www.bbc.co.uk/news/10628494",
        "layer": "document_discovery",
    },
    "ap_news": {
        "keys": [], "auth": "none",
        "endpoint": "https://apnews.com/hub/ap-top-news?format=feed&type=rss",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://apnews.com",
        "layer": "document_discovery",
        "note": "rsshub 403 → AP official RSS/Atom feed (2026-06-03)",
    },
    "techcrunch": {
        "keys": [], "auth": "none",
        "endpoint": "https://techcrunch.com/feed/",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://techcrunch.com",
        "layer": "document_discovery",
    },
    "the_verge": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.theverge.com/rss/index.xml",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://www.theverge.com",
        "layer": "document_discovery",
    },
    "zdnet_korea": {
        "keys": [], "auth": "none",
        "endpoint": "https://zdnet.co.kr",
        "free_plan": "Public HTML — no key required",
        "docs_url": "https://zdnet.co.kr",
        "layer": "document_discovery",
    },
    "etnews": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.etnews.com",
        "free_plan": "Public HTML — no key required",
        "docs_url": "https://www.etnews.com",
        "layer": "document_discovery",
    },
    "yna": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.yna.co.kr/rss/news.xml",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://www.yna.co.kr",
        "layer": "document_discovery",
    },
    "hankyung": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.hankyung.com/feed/all-news",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://www.hankyung.com",
        "layer": "document_discovery",
    },
    "maekyung": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.mk.co.kr/rss/30000001/",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://www.mk.co.kr",
        "layer": "document_discovery",
    },
    "aljazeera": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.aljazeera.com/xml/rss/all.xml",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://www.aljazeera.com",
        "layer": "document_discovery",
    },
    # ── Phase 2: 커뮤니티/소셜 ───────────────────────────────────────────────
    "reddit": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.reddit.com/r/worldnews.json",
        "free_plan": "Public .json endpoint — no key for read-only",
        "docs_url": "https://www.reddit.com/dev/api",
        "layer": "community_signal",
        "note": "Write API excluded (deferred)",
    },
    "hacker_news": {
        "keys": [], "auth": "none",
        "endpoint": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "free_plan": "Public Firebase API — no key required",
        "docs_url": "https://github.com/HackerNews/API",
        "layer": "community_signal",
    },
    "product_hunt": {
        "keys": ["PRODUCT_HUNT_ACCESS_TOKEN"], "auth": "bearer_token",
        "endpoint": "https://api.producthunt.com/v2/api/graphql",
        "free_plan": "Free developer token: ~1000 req/day",
        "docs_url": "https://api.producthunt.com/v2/docs",
        "layer": "community_signal",
        "note": "Alias: PRODUCT_HUNT_API_KEY->PRODUCT_HUNT_ACCESS_TOKEN",
    },
    "youtube": {
        "keys": ["YOUTUBE_API_KEY"], "auth": "query_param_key",
        "endpoint": "https://www.googleapis.com/youtube/v3/search",
        "free_plan": "Free: 10,000 quota units/day via Google Cloud Console",
        "docs_url": "https://developers.google.com/youtube/v3/docs",
        "layer": "community_signal",
    },
    "dcinside": {
        "keys": [], "auth": "none",
        "endpoint": "https://gall.dcinside.com",
        "free_plan": "Public HTML — no key required",
        "docs_url": "https://gall.dcinside.com",
        "layer": "community_signal",
    },
    "fmkorea": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.fmkorea.com",
        "free_plan": "Public HTML — no key required",
        "docs_url": "https://www.fmkorea.com",
        "layer": "community_signal",
    },
    "naver_blog_search": {
        "keys": ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"], "auth": "header_x_naver",
        "endpoint": "https://openapi.naver.com/v1/search/blog.json",
        "free_plan": "Free: 25,000 calls/day; register at developers.naver.com",
        "docs_url": "https://developers.naver.com/docs/serviceapi/search/blog/blog.md",
        "layer": "search_enrichment",
        "note": "Alias: CLIENT_ID→NAVER_CLIENT_ID, CLIENT_SECRET→NAVER_CLIENT_SECRET",
    },
    "x": {
        "keys": [], "auth": "login_required",
        "endpoint": "https://twitter.com",
        "free_plan": "BLOCKED — login wall / bearer token required",
        "docs_url": "https://developer.twitter.com",
        "layer": "community_signal",
        "status_override": "LOGIN_WALL",
        "error_category_override": "LOGIN_WALL",
        "note": "Excluded Round 1 — login required",
    },
    "cnbc": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://www.cnbc.com",
        "layer": "document_discovery",
    },
    "blind": {
        "keys": [], "auth": "login_required",
        "endpoint": "https://www.teamblind.com",
        "free_plan": "BLOCKED — login wall",
        "docs_url": "https://www.teamblind.com",
        "layer": "community_signal",
        "status_override": "LOGIN_WALL",
        "error_category_override": "LOGIN_WALL",
        "note": "Excluded Round 1 — login required",
    },
    # ── Phase 3: 공식/데이터 ─────────────────────────────────────────────────
    "gdelt": {
        "keys": [], "auth": "none",
        "endpoint": "https://api.gdeltproject.org/api/v2/doc/doc",
        "free_plan": "Public API — no key; rate limit UNKNOWN",
        "docs_url": "https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/",
        "layer": "official_evidence",
    },
    "opendart": {
        "keys": ["OPENDART_API_KEY"], "auth": "query_param_crtfc_key",
        "endpoint": "https://opendart.fss.or.kr/api/list.json",
        "free_plan": "Free: ~10,000 req/day; 40-char key at opendart.fss.or.kr",
        "docs_url": "https://opendart.fss.or.kr/guide/main.do",
        "layer": "official_evidence",
    },
    "sec_edgar": {
        "keys": [], "auth": "none",
        "endpoint": "https://efts.sec.gov/LATEST/search-index",
        "free_plan": "Public API — no key; 10 req/s limit; User-Agent required",
        "docs_url": "https://efts.sec.gov",
        "layer": "official_evidence",
    },
    "krx_kind": {
        "keys": [], "auth": "none_public_html",
        "endpoint": "https://kind.krx.co.kr/disclosure/todaydisclosure.do",
        "free_plan": "Public HTML — Playwright required (JS render)",
        "docs_url": "https://kind.krx.co.kr",
        "layer": "official_evidence",
        "status_override": "PLAYWRIGHT_REQUIRED",
        "error_category_override": "PLAYWRIGHT_REQUIRED",
        "note": "Deferred to Round 2 — requires Playwright",
    },
    "bok_ecos": {
        "keys": ["BOK_ECOS_API_KEY"], "auth": "query_param_apiKey",
        "endpoint": "https://ecos.bok.or.kr/api/StatisticTableList/apiKey/json/kr/1/5/",
        "free_plan": "Free key at ecos.bok.or.kr/api/#/AuthKeyApply; quota UNKNOWN",
        "docs_url": "https://ecos.bok.or.kr/api/",
        "layer": "official_evidence",
        "note": "Alias: ECOS_API_KEY→BOK_ECOS_API_KEY",
    },
    "eia": {
        "keys": ["EIA_API_KEY"], "auth": "query_param_api_key",
        "endpoint": "https://api.eia.gov/v2/",
        "free_plan": "Free: 5000 req/day; register at eia.gov/opendata/register.php",
        "docs_url": "https://www.eia.gov/opendata/",
        "layer": "official_evidence",
    },
    "federal_register": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.federalregister.gov/api/v1/articles.json",
        "free_plan": "Public API — no key required",
        "docs_url": "https://www.federalregister.gov/reader-aids/developer-resources",
        "layer": "official_evidence",
    },
    "eu_press_corner": {
        "keys": [], "auth": "none_public_html",
        "endpoint": "https://ec.europa.eu/commission/presscorner/home/en",
        "free_plan": "Public HTML — Playwright required (JS render)",
        "docs_url": "https://ec.europa.eu/commission/presscorner",
        "layer": "official_evidence",
        "status_override": "PLAYWRIGHT_REQUIRED",
        "error_category_override": "PLAYWRIGHT_REQUIRED",
        "note": "Deferred to Round 2 — requires Playwright; no official API endpoint",
    },
    "naver_news_search": {
        "keys": ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"], "auth": "header_x_naver",
        "endpoint": "https://openapi.naver.com/v1/search/news.json",
        "free_plan": "Free: 25,000 calls/day; same key as naver_blog_search",
        "docs_url": "https://developers.naver.com/docs/serviceapi/search/news/news.md",
        "layer": "search_enrichment",
    },
    "reuters": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.reutersagency.com/feed/",
        "free_plan": "Deferred — licensing review required",
        "docs_url": "https://www.reutersagency.com",
        "layer": "news_verification",
        "status_override": "LICENSE_REQUIRED",
        "error_category_override": "LICENSE_REQUIRED",
        "note": "Excluded Round 1 — licensing uncertainty; NEEDS_LICENSE_OR_API",
    },
    # ── Phase 4 확장 후보: search_enrichment ─────────────────────────────────
    "google_programmable_search": {
        "keys": ["GOOGLE_CUSTOM_SEARCH_API_KEY", "GOOGLE_CUSTOM_SEARCH_CX"],
        "auth": "query_param_key",
        "endpoint": "https://www.googleapis.com/customsearch/v1",
        "free_plan": "Free: 100 queries/day; $5/1000 after; via Google Cloud Console",
        "docs_url": "https://developers.google.com/custom-search/v1/overview",
        "layer": "search_enrichment",
        "status_override": "DEPRECATED_OR_EXCLUDED",
        "error_category_override": "DEPRECATED_OR_EXCLUDED",
        "note": "Excluded MVP: 400 on all probes; reactivate when CX+key confirmed working. Code/spec/alias preserved.",
    },
    "serper": {
        "keys": ["SERPER_API_KEY"],
        "auth": "header_x_api_key",
        "endpoint": "https://google.serper.dev/search",
        "free_plan": "Free: 2500 queries (one-time credit); paid plans after",
        "docs_url": "https://serper.dev/api-key",
        "layer": "search_enrichment",
    },
    "tavily": {
        "keys": ["TAVILY_API_KEY"],
        "auth": "bearer_token",
        "endpoint": "https://api.tavily.com/search",
        "free_plan": "Free: 1000 requests/month",
        "docs_url": "https://app.tavily.com",
        "layer": "search_enrichment",
    },
    "exa": {
        "keys": ["EXA_API_KEY"],
        "auth": "bearer_token",
        "endpoint": "https://api.exa.ai/search",
        "free_plan": "Free: 1000 requests/month",
        "docs_url": "https://dashboard.exa.ai",
        "layer": "search_enrichment",
    },
    "newsapi": {
        "keys": ["NEWSAPI_API_KEY"],
        "auth": "query_param_apiKey",
        "endpoint": "https://newsapi.org/v2/top-headlines",
        "free_plan": "Developer: 100 req/day; no commercial use on free plan",
        "docs_url": "https://newsapi.org/docs",
        "layer": "search_enrichment",
        "note": "Commercial use requires paid plan",
    },
    "gnews": {
        "keys": ["GNEWS_API_KEY"],
        "auth": "query_param_token",
        "endpoint": "https://gnews.io/api/v4/top-headlines",
        "free_plan": "Free: 100 requests/day, 10 articles/request",
        "docs_url": "https://gnews.io/docs/",
        "layer": "search_enrichment",
    },
    "guardian": {
        "keys": ["GUARDIAN_API_KEY"],
        "auth": "query_param_api-key",
        "endpoint": "https://content.guardianapis.com/search",
        "free_plan": "Free: 5000 calls/day; no commercial redistribution",
        "docs_url": "https://open-platform.theguardian.com/access/",
        "layer": "search_enrichment",
        "note": "Terms prohibit commercial redistribution of full content",
    },
    "nyt": {
        "keys": ["NYT_API_KEY"],
        "auth": "query_param_api-key",
        "endpoint": "https://api.nytimes.com/svc/search/v2/articlesearch.json",
        "free_plan": "Free: 500 req/day; no commercial use without agreement",
        "docs_url": "https://developer.nytimes.com/",
        "layer": "search_enrichment",
        "note": "Commercial redistribution requires separate licensing agreement",
    },
    # ── Phase 4 확장 후보: fast_signal (external, key 없음) ─────────────────
    "google_trending_now": {
        "keys": [], "auth": "none",
        "endpoint": "https://trends.google.com/trends/trendingsearches/daily",
        "free_plan": "Unofficial — no official JSON API; HTML/RSS parse only",
        "docs_url": "https://trends.google.com",
        "layer": "fast_signal",
        "signal_type": "external",
        "status_override": "EXTERNAL_SIGNAL_SOURCE",
        "error_category_override": "EXTERNAL_SIGNAL_SOURCE",
        "note": "No official API key; unofficial scrape; low evidence; rate limit UNKNOWN",
    },
    "signal_bz": {
        "keys": [], "auth": "none",
        "endpoint": "https://www.signal.bz/",
        "free_plan": "Unofficial — Korean trending keywords; no official API",
        "docs_url": "https://www.signal.bz/",
        "layer": "fast_signal",
        "signal_type": "external",
        "status_override": "EXTERNAL_SIGNAL_SOURCE",
        "error_category_override": "EXTERNAL_SIGNAL_SOURCE",
        "note": "Korean real-time search trend aggregator; no official API; low evidence",
    },
    "loword": {
        "keys": [], "auth": "none",
        "endpoint": "https://loword.co.kr/",
        "free_plan": "Unofficial — Korean trending keywords from Naver/Google; no official API",
        "docs_url": "https://knowledge.loword.co.kr/func/reality",
        "layer": "fast_signal",
        "signal_type": "external",
        "status_override": "EXTERNAL_SIGNAL_SOURCE",
        "error_category_override": "EXTERNAL_SIGNAL_SOURCE",
        "note": "Aggregates Naver+Google trending; no official API; low evidence",
    },
    # ── Phase 4 확장 후보: market_signal ────────────────────────────────────
    "finnhub": {
        "keys": ["FINNHUB_API_KEY"],
        "auth": "query_param_token",
        "endpoint": "https://finnhub.io/api/v1/quote",
        "free_plan": "Free: 60 req/min; real-time US stocks",
        "docs_url": "https://finnhub.io/docs/api",
        "layer": "market_signal",
    },
    "twelve_data": {
        "keys": ["TWELVE_DATA_API_KEY"],
        "auth": "query_param_apikey",
        "endpoint": "https://api.twelvedata.com/time_series",
        "free_plan": "Free: 800 credits/day",
        "docs_url": "https://twelvedata.com/docs",
        "layer": "market_signal",
    },
    "alpha_vantage": {
        "keys": ["ALPHA_VANTAGE_API_KEY"],
        "auth": "query_param_apikey",
        "endpoint": "https://www.alphavantage.co/query",
        "free_plan": "Free: 25 requests/day (as of 2025; verify current limit)",
        "docs_url": "https://www.alphavantage.co/documentation/",
        "layer": "market_signal",
    },
    "polygon": {
        "keys": ["POLYGON_API_KEY"],
        "auth": "bearer_token",
        "endpoint": "https://api.polygon.io/v2/aggs/ticker/AAPL/prev",
        "free_plan": "Free: unlimited prev-day data; real-time requires paid plan",
        "docs_url": "https://polygon.io/docs/stocks",
        "layer": "market_signal",
    },
    "coinbase_market": {
        "keys": [], "auth": "none",
        "endpoint": "https://api.coinbase.com/api/v3/brokerage/market/products",
        "free_plan": "Public market data — no key required",
        "docs_url": "https://docs.cdp.coinbase.com/advanced-trade/reference/",
        "layer": "market_signal",
    },
    "binance_market": {
        "keys": [], "auth": "none",
        "endpoint": "https://api.binance.com/api/v3/ticker/price",
        "free_plan": "Public market data — no key required; 1200 req/min weight limit",
        "docs_url": "https://binance-docs.github.io/apidocs/spot/en/",
        "layer": "market_signal",
    },
    # ── Phase 4 확장 후보: domain_signal ─────────────────────────────────────
    "kma": {
        "keys": ["KMA_API_KEY"],
        "auth": "query_param_serviceKey",
        "endpoint": "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst",
        "free_plan": "Free via data.go.kr (기상청 단기예보 조회서비스)",
        "docs_url": "https://www.data.go.kr/data/15084084/openapi.do",
        "layer": "domain_signal",
        "note": "data.go.kr 발급 serviceKey 전용. apihub.kma.go.kr는 별도 authKey 발급 필요(현재 키로 401) — 2026-06-12 실측",
    },
    "tour": {
        "keys": ["TOUR_API_KEY"],
        "auth": "query_param_serviceKey",
        "endpoint": "https://apis.data.go.kr/B551011/KorService2/areaBasedList2",
        "free_plan": "Free via data.go.kr; quota UNKNOWN",
        "docs_url": "https://api.visitkorea.or.kr/",
        "layer": "domain_signal",
        "note": "한국관광공사 TourAPI; KorService1 폐기 → KorService2/areaBasedList2 (2026-06-12 경로 검증)",
    },
    "its": {
        "keys": ["ITS_API_KEY"],
        "auth": "query_param_apiKey",
        "endpoint": "https://openapi.its.go.kr:9443/trafficInfo",
        "free_plan": "Free via its.go.kr; quota UNKNOWN",
        "docs_url": "https://www.its.go.kr/opendata/opendataList",
        "layer": "domain_signal",
        "note": "국가교통정보센터 REST: /trafficInfo + apiKey/type/minX..maxY/getType=json (구 NCMInfra 경로는 4004 잘못된 URL)",
    },
    "kofic": {
        "keys": ["KOFIC_API_KEY"],
        "auth": "query_param_key",
        "endpoint": "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json",
        "free_plan": "Free: open API (비상업적 이용); key via kobis.or.kr",
        "docs_url": "https://www.kobis.or.kr/kobisopenapi/homepg/main/main.do",
        "layer": "domain_signal",
        "note": "영화진흥위원회 KOBIS 오픈API; env key name: KOFIC_API_KEY",
    },
    "tmdb": {
        "keys": ["TMDB_API_KEY"],
        "auth": "query_param_api_key",
        "endpoint": "https://api.themoviedb.org/3/movie/popular",
        "free_plan": "Free: ~100 requests/hour (generous); no commercial cap on metadata",
        "docs_url": "https://developers.themoviedb.org/3/getting-started/introduction",
        "layer": "domain_signal",
    },
    "kopis": {
        "keys": ["KOPIS_API_KEY"],
        "auth": "query_param_service",
        "endpoint": "https://kopis.or.kr/openApi/restful/pblprfr",
        "free_plan": "Free via kopis.or.kr; quota UNKNOWN",
        "docs_url": "https://kopis.or.kr/openApi/restful/pblprfr",
        "layer": "domain_signal",
        "note": "공연예술통합전산망; key via kopis.or.kr 회원가입; quota UNKNOWN",
    },
    "aladin": {
        "keys": ["ALADIN_TTB_KEY"],
        "auth": "query_param_TTBKey",
        "endpoint": "https://www.aladin.co.kr/ttb/api/ItemList.aspx",
        "free_plan": "Free for personal use; commercial restrictions apply",
        "docs_url": "https://www.aladin.co.kr/ttb/wblog/IndividualInfo.aspx",
        "layer": "domain_signal",
        "note": "알라딘 Open API (TTB); personal use only; commercial requires agreement",
    },
    "igdb": {
        "keys": ["IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET"],
        "auth": "igdb_client_credentials",
        "endpoint": "https://api.igdb.com/v4/games",
        "free_plan": "Free: 4 req/sec; unlimited total via Twitch app access token",
        "docs_url": "https://api-docs.igdb.com/",
        "layer": "domain_signal",
        "note": "Twitch OAuth2 client_credentials: IGDB_CLIENT_ID + IGDB_CLIENT_SECRET → access token exchange",
    },
    "culture_info": {
        "keys": ["CULTURE_INFO_API_KEY"],
        "auth": "query_param_serviceKey",
        "endpoint": "https://apis.data.go.kr/B553457/cultureinfo/period2",
        "free_plan": "Free via data.go.kr (개발계정 10,000건); 한눈에보는문화정보조회서비스",
        "docs_url": "https://www.data.go.kr/data/15138937/openapi.do",
        "layer": "domain_signal",
        "note": "구 culture.go.kr REST 경로 폐기(HTML 에러페이지) → data.go.kr B553457/cultureinfo/period2 (2026-06-12 경로 검증)",
    },
}


def _run_dry_check(service_id: str, config: dict) -> dict:
    """Dry-run: key presence check and policy meta output. No actual API call."""
    base = {
        "service": service_id,
        "http_status": None,
        "docs_url": config.get("docs_url", ""),
        "free_plan_summary": config.get("free_plan", ""),
        "layer": config.get("layer", ""),
        "note": config.get("note", ""),
    }

    if override := config.get("status_override"):
        if override == "EXTERNAL_SIGNAL_SOURCE":
            return {
                **base,
                "status": "EXTERNAL_SIGNAL_SOURCE",
                "error_category": "EXTERNAL_SIGNAL_SOURCE",
                "keys_checked": [],
                "next_action": "assess_scrape_feasibility_separately",
            }
        return {
            **base,
            "status": override,
            "error_category": config.get("error_category_override", override),
            "keys_checked": [],
            "next_action": "see_note_above",
        }

    keys_needed = config.get("keys", [])
    if not keys_needed:
        return {
            **base,
            "status": "NO_KEY_REQUIRED",
            "error_category": None,
            "keys_checked": [],
            "next_action": "ready_for_live_test",
        }

    status_map = env_status(keys_needed)
    all_present = all(v == "present" for v in status_map.values())

    if all_present:
        return {
            **base,
            "status": "KEY_PRESENT_DRY_RUN",
            "error_category": None,
            "keys_checked": list(status_map.keys()),
            "next_action": "run_with_--live_to_test",
        }

    missing = [k for k, v in status_map.items() if v == "missing"]
    return {
        **base,
        "status": "MISSING_KEY",
        "error_category": "MISSING_KEY",
        "keys_checked": list(status_map.keys()),
        "next_action": f"set_in_.env: {', '.join(missing)}",
    }


def _generate_report(results: list[dict], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)

    jsonl_dir = report_dir.parent.parent / "outputs" / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = jsonl_dir / "api_connectivity_results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    md_path = report_dir / "api_connectivity_report.md"
    lines = [
        "# API Connectivity Report (Dry-Run)",
        "",
        f"Services checked: {len(results)}",
        "",
        "| Service | Layer | Status | Error | Free Plan | Next Action |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        plan = r["free_plan_summary"][:45] + ("…" if len(r["free_plan_summary"]) > 45 else "")
        lines.append(
            f"| {r['service']} | {r['layer']} | {r['status']} "
            f"| {r['error_category'] or '—'} | {plan} | {r['next_action']} |"
        )
    lines += [
        "",
        "## Legend",
        "- `NO_KEY_REQUIRED` — public endpoint, ready to test live",
        "- `KEY_PRESENT_DRY_RUN` — key found in env; run `--live` to probe",
        "- `MISSING_KEY` — add key to .env to proceed",
        "- `LOGIN_WALL` — login/auth required; excluded Round 1",
        "- `PLAYWRIGHT_REQUIRED` — JS render needed; deferred to Round 2",
        "- `LICENSE_REQUIRED` — licensing review needed; deferred",
        "- `EXTERNAL_SIGNAL_SOURCE` — no API key; external scrape signal; low evidence",
        "- `DEFERRED_LIVE_TEST` — key present but live test explicitly deferred",
        "",
        "## Security",
        "Dry-run expanded source coverage report. NO API keys, tokens, or secret values.",
        "Run `--live` (requires explicit user approval) for actual probes.",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, jsonl_path


def main() -> None:
    parser = argparse.ArgumentParser(description="API connectivity check for ingestion sources")
    parser.add_argument("--env-path", default=None, help="Path to .env file (default: repo root)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Key presence check only — no HTTP calls (default)")
    parser.add_argument("--live", action="store_true", default=False,
                        help="Live HTTP probe — NOT implemented in Round 1")
    parser.add_argument("--service", default=None,
                        help="Check a single service by source ID")
    parser.add_argument("--all", dest="all_services", action="store_true",
                        help="Check all services (default)")
    parser.add_argument("--max-calls-per-service", type=int, default=1,
                        help="Max API calls per service in live mode (unused in Round 1)")
    args = parser.parse_args()

    if args.live:
        print("WARNING: --live mode is not implemented in Round 1. Running dry-run.")

    if args.env_path:
        load_env(Path(args.env_path))

    if args.service:
        if args.service not in _SERVICE_CONFIGS:
            print(f"Unknown service '{args.service}'. Available: {', '.join(_SERVICE_CONFIGS)}")
            sys.exit(1)
        services = {args.service: _SERVICE_CONFIGS[args.service]}
    else:
        services = _SERVICE_CONFIGS

    results = []
    for sid, cfg in services.items():
        r = _run_dry_check(sid, cfg)
        icon = "OK" if r["status"] in ("NO_KEY_REQUIRED", "KEY_PRESENT_DRY_RUN") else "--"
        print(f"{icon} {sid:28s}  {r['status']}")
        results.append(r)

    report_dir = Path(__file__).parent.parent / "outputs" / "reports"
    md_path, jsonl_path = _generate_report(results, report_dir)
    print(f"\nReport : {md_path}")
    print(f"JSONL  : {jsonl_path}")

    missing = sum(1 for r in results if r["error_category"] == "MISSING_KEY")
    ready = sum(1 for r in results if r["status"] in ("NO_KEY_REQUIRED", "KEY_PRESENT_DRY_RUN"))
    deferred = sum(1 for r in results if r["status"] in (
        "LOGIN_WALL", "PLAYWRIGHT_REQUIRED", "LICENSE_REQUIRED"))
    external = sum(1 for r in results if r["status"] == "EXTERNAL_SIGNAL_SOURCE")
    print(
        f"\nTotal: {len(results)}  Ready: {ready}  Missing key: {missing}"
        f"  Deferred: {deferred}  External: {external}"
    )


if __name__ == "__main__":
    main()
