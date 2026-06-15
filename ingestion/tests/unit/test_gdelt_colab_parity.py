"""G-3: GDELT Colab-parity audit — endpoint/params 일치 + host rate-limit governor + spaced probe."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.orchestration.gdelt_strategy import collect_gdelt
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.orchestration.vendor_api_routes import (
    _GDELT_BASE,
    VendorRouteResult,
    fetch_gdelt,
)

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_colab_profile_endpoint_and_params_match():
    """현재 오케스트레이션이 Colab DOC 2.0 ArtList 프로파일과 동일한 호출을 하는지."""
    seen = {}
    def _get(url, params=None):
        seen["url"] = url; seen["params"] = params
        return 200, {"articles": [{"url": "https://x/a", "title": "T", "seendate": "20260615T120000Z"}]}, None
    res = fetch_gdelt(http_get=_get, query="economy", limit=3, timespan="1d")
    assert seen["url"] == _GDELT_BASE == "https://api.gdeltproject.org/api/v2/doc/doc"
    assert seen["params"]["mode"] == "ArtList" and seen["params"]["format"] == "json"
    assert seen["params"]["maxrecords"] == "3" and seen["params"]["timespan"] == "1d"
    assert res.success and res.item_count == 1


def test_host_level_rate_limit_lock_blocks_call():
    """cooldown 활성 시 vendor_fetch를 호출하지 않고 pending_resume."""
    gov = RateLimitGovernor(state_path=None)
    gov.record_rate_limited("gdelt", reason="provider_429", now=_NOW)
    calls = {"n": 0}
    def _fetch(**kw):
        calls["n"] += 1
        return VendorRouteResult("gdelt", "r", True, 200, "official_record", (), None, 0)
    res = collect_gdelt(governor=gov, vendor_fetch=_fetch, now=_NOW, sleep=lambda s: None)
    assert res.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
    assert calls["n"] == 0          # host-level lock: 호출 0 (tight-loop 금지)


def test_persisted_last_call_at_enforces_interval():
    gov = RateLimitGovernor(state_path=None)
    gov.record_call("gdelt", now=_NOW)
    d = gov.decide("gdelt", min_interval_seconds=10, now=_NOW + timedelta(seconds=5))
    assert d.allowed is False       # 직전 호출 후 간격 미충족


def test_query_simplification_advances_on_empty():
    """broad가 비면 다음 단순 query로 진행(429 아님)."""
    seq = []
    def _fetch(*, query, limit, timespan):
        seq.append(query)
        ok = len(seq) >= 2          # 2번째 query에서 성공
        recs = ({"record_type": "official_record"},) if ok else ()
        return VendorRouteResult("gdelt", "r", ok, 200, "official_record", recs, None if ok else "http_200_no_articles", len(recs))
    gov = RateLimitGovernor(state_path=None)
    res = collect_gdelt(governor=gov, vendor_fetch=_fetch, now=_NOW, sleep=lambda s: None, max_probes=3)
    assert res.success and len(seq) >= 2       # 단순화 ladder 진행


def test_429_becomes_pending_resume():
    def _fetch(**kw):
        return VendorRouteResult("gdelt", "r", False, 429, "official_record", (), "provider_rate_limited", 0)
    gov = RateLimitGovernor(state_path=None)
    res = collect_gdelt(governor=gov, vendor_fetch=_fetch, now=_NOW, sleep=lambda s: None)
    assert res.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
    assert res.next_resume_at is not None       # cooldown 저장 → 자동 재개
