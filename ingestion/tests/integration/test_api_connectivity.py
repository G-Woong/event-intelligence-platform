from __future__ import annotations

import pytest

from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS, _run_dry_check

pytestmark = pytest.mark.integration

# Dry-run by default: key presence check only, no HTTP calls.
# pytest -m "integration"          → all dry-run checks below
# pytest -m "live_api"             → actual HTTP probes (Round 2)
# Missing keys → SKIP (not FAIL)


# ── Phase 3: Official / Data APIs ─────────────────────────────────────────

# OpenDart — https://opendart.fss.or.kr/guide/main.do
# Auth   : crtfc_key query param (40-char hex, email-verified free key)
# Free   : ~10,000 req/day (sources differ; treat as UNKNOWN until verified)
# Errors : status 010=missing key, 020=invalid key, 100=quota exceeded
@pytest.mark.parametrize("service_id", ["opendart"])
def test_opendart_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    if r["status"] == "MISSING_KEY":
        pytest.skip(f"{service_id}: OPENDART_API_KEY not set — MISSING")
    assert r["status"] in ("KEY_PRESENT_DRY_RUN", "NO_KEY_REQUIRED")


# BOK ECOS — https://ecos.bok.or.kr/api/
# Auth   : apiKey query param; key at ecos.bok.or.kr/api/#/AuthKeyApply
# Free   : daily quota UNKNOWN (docs do not specify; estimated 1000–5000 req/day)
# Errors : HTTP 400 with message body on invalid key
@pytest.mark.parametrize("service_id", ["bok_ecos"])
def test_bok_ecos_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    if r["status"] == "MISSING_KEY":
        pytest.skip(f"{service_id}: BOK_ECOS_API_KEY (alias ECOS_API_KEY) not set — MISSING")


# EIA — https://www.eia.gov/opendata/
# Auth   : api_key query param; free key at eia.gov/opendata/register.php
# Free   : 5,000 requests/day
# Errors : HTTP 403 on invalid/missing key
@pytest.mark.parametrize("service_id", ["eia"])
def test_eia_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    if r["status"] == "MISSING_KEY":
        pytest.skip(f"{service_id}: EIA_API_KEY not set — MISSING")


# ── Phase 2: Community / Social APIs ──────────────────────────────────────

# YouTube Data API v3 — https://developers.google.com/youtube/v3/docs
# Auth   : api_key query param or OAuth2; key via Google Cloud Console
# Free   : 10,000 quota units/day
# Errors : HTTP 403 quotaExceeded, 400 keyInvalid
@pytest.mark.parametrize("service_id", ["youtube"])
def test_youtube_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    if r["status"] == "MISSING_KEY":
        pytest.skip(f"{service_id}: YOUTUBE_API_KEY not set — MISSING")


# Naver Search API — https://developers.naver.com/docs/serviceapi/search/
# Auth   : X-Naver-Client-Id + X-Naver-Client-Secret headers
# Free   : 25,000 calls/day per service (blog, news separate quotas)
# Aliases: CLIENT_ID→NAVER_CLIENT_ID, CLIENT_SECRET→NAVER_CLIENT_SECRET
@pytest.mark.parametrize("service_id", ["naver_blog_search", "naver_news_search"])
def test_naver_search_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    if r["status"] == "MISSING_KEY":
        pytest.skip(f"{service_id}: NAVER_CLIENT_ID/SECRET (alias CLIENT_ID/SECRET) not set")


# Product Hunt API — https://api.producthunt.com/v2/docs
# Auth   : Bearer developer token; obtain at producthunt.com/v2/oauth/applications
# Free   : ~1,000 requests/day for developer tokens
# Errors : HTTP 401 on missing/invalid token
@pytest.mark.parametrize("service_id", ["product_hunt"])
def test_product_hunt_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    if r["status"] == "MISSING_KEY":
        pytest.skip(
            f"{service_id}: PRODUCT_HUNT_ACCESS_TOKEN (alias PRODUCT_HUNT_API_KEY) not set"
        )


# ── Phase 1 & 3: Public no-auth sources ───────────────────────────────────

# Hacker News Firebase — https://github.com/HackerNews/API — public, no key
# GDELT v2 — https://blog.gdeltproject.org/ — public, no key, rate limit UNKNOWN
# SEC EDGAR — https://efts.sec.gov — public, 10 req/s, requires User-Agent header
# Federal Register — https://federalregister.gov/api/v1 — public, no key
# BBC RSS — public; AP News RSS — public; etc.
@pytest.mark.parametrize("service_id", [
    "bbc", "ap_news", "techcrunch", "the_verge", "zdnet_korea",
    "etnews", "yna", "hankyung", "maekyung", "aljazeera",
    "hacker_news", "reddit", "dcinside", "fmkorea", "cnbc",
    "gdelt", "sec_edgar", "federal_register",
    # eu_press_corner moved to deferred (PLAYWRIGHT_REQUIRED)
])
def test_no_key_sources_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    assert r["status"] == "NO_KEY_REQUIRED"
    assert r["error_category"] is None


# ── Deferred / Blocked sources ─────────────────────────────────────────────

# X (Twitter) — bearer token or login required → BLOCKED Round 1
# Blind — login required → BLOCKED Round 1
# Reuters — licensing review → DEFERRED Round 1
# KRX KIND — Playwright required → DEFERRED Round 2
@pytest.mark.parametrize("service_id,expected_status", [
    ("x", "LOGIN_WALL"),
    ("blind", "LOGIN_WALL"),
    ("reuters", "LICENSE_REQUIRED"),
    ("krx_kind", "PLAYWRIGHT_REQUIRED"),
    ("eu_press_corner", "PLAYWRIGHT_REQUIRED"),
])
def test_deferred_sources_status(service_id, expected_status):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    assert r["status"] == expected_status
    assert r["error_category"] == expected_status


# ── Phase 4 확장 소스: external signal ─────────────────────────────────────

@pytest.mark.parametrize("service_id", [
    "google_trending_now", "signal_bz", "loword",
])
def test_external_signal_sources_status(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    assert r["status"] == "EXTERNAL_SIGNAL_SOURCE"
    assert r["error_category"] == "EXTERNAL_SIGNAL_SOURCE"


# ── Phase 4 확장 소스: key-required (skip if missing) ─────────────────────

@pytest.mark.parametrize("service_id", [
    # google_programmable_search removed: status_override=DEPRECATED_OR_EXCLUDED
    "serper", "tavily", "exa",
    "newsapi", "gnews", "guardian", "nyt",
    "finnhub", "twelve_data", "alpha_vantage", "polygon",
    "kma", "tour", "its", "kofic", "tmdb", "kopis", "aladin", "igdb",
    "culture_info",
])
def test_phase4_key_sources_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    if r["status"] == "MISSING_KEY":
        pytest.skip(f"{service_id}: key(s) not set in .env")
    assert r["status"] in ("KEY_PRESENT_DRY_RUN", "NO_KEY_REQUIRED")


@pytest.mark.parametrize("service_id", [
    "coinbase_market", "binance_market",
])
def test_phase4_no_key_sources_dry_run(service_id):
    r = _run_dry_check(service_id, _SERVICE_CONFIGS[service_id])
    assert r["service"] == service_id
    assert r["status"] == "NO_KEY_REQUIRED"


# ── Security invariant ─────────────────────────────────────────────────────

def test_dry_run_output_contains_no_secrets():
    """All dry-run results must only contain 'present'/'missing' — never actual key values."""
    secret_like_patterns = [
        "sk-", "Bearer ", "apikey=", "crtfc_key=", "api_key=",
    ]
    for sid, cfg in _SERVICE_CONFIGS.items():
        r = _run_dry_check(sid, cfg)
        result_str = json_safe_str(r)
        for pattern in secret_like_patterns:
            assert pattern not in result_str, (
                f"{sid}: result contained secret-like pattern '{pattern}'"
            )


def json_safe_str(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
