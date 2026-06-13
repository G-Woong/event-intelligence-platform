from __future__ import annotations

import json
import pytest

from ingestion.probes.models import PROBE_STATUS, ProbeResult


def test_probe_status_is_frozenset():
    assert isinstance(PROBE_STATUS, frozenset)


def test_probe_status_contains_required_statuses():
    required = {
        "LIVE_SUCCESS", "LIVE_PARTIAL", "MISSING_KEY", "INVALID_KEY",
        "PERMISSION_DENIED", "RATE_LIMITED", "QUOTA_EXHAUSTED", "PLAN_RESTRICTED",
        "ENDPOINT_DEPRECATED", "SCHEMA_CHANGED", "PARSE_ERROR", "NETWORK_ERROR",
        "TIMEOUT", "BLOCKED", "DEFERRED", "UNKNOWN",
    }
    assert required <= PROBE_STATUS


def test_probe_result_minimal_construction():
    r = ProbeResult(source_id="test_svc", method="api", status="UNKNOWN")
    assert r.source_id == "test_svc"
    assert r.method == "api"
    assert r.status == "UNKNOWN"
    assert r.items_found == 0
    assert r.meaningful_fields == []
    assert r.artifact_paths == {}


def test_probe_result_full_construction():
    r = ProbeResult(
        source_id="naver_news_search",
        method="api",
        query="테스트",
        region="KR",
        status="LIVE_SUCCESS",
        http_status=200,
        items_found=3,
        items_extracted=3,
        meaningful_fields=["items", "total"],
        artifact_paths={"raw_payload": "/tmp/raw.json"},
        error_category=None,
        next_action="integrate_into_pipeline",
    )
    assert r.status == "LIVE_SUCCESS"
    assert r.http_status == 200
    assert r.items_found == 3


def test_probe_result_to_dict_serialisable():
    r = ProbeResult(
        source_id="gdelt",
        method="api",
        status="LIVE_SUCCESS",
        http_status=200,
        items_found=5,
        meaningful_fields=["articles"],
        artifact_paths={"raw_payload": "/some/path.json"},
    )
    d = r.to_dict()
    # Must be JSON-serialisable
    text = json.dumps(d)
    assert "gdelt" in text
    assert "LIVE_SUCCESS" in text


def test_probe_result_invalid_status_raises():
    with pytest.raises(ValueError, match="Invalid status"):
        ProbeResult(source_id="x", method="api", status="MADE_UP_STATUS")


def test_probe_result_artifact_paths_as_strings():
    from pathlib import Path
    p = Path("/tmp/ss.png")
    r = ProbeResult(
        source_id="test",
        method="playwright",
        status="LIVE_SUCCESS",
        artifact_paths={"screenshot": p},
    )
    d = r.to_dict()
    assert d["artifact_paths"]["screenshot"] == str(p)


def test_probe_result_blocked_status():
    r = ProbeResult(source_id="x", method="playwright", status="BLOCKED", error_category="CAPTCHA_DETECTED")
    assert r.status == "BLOCKED"
    assert r.error_category == "CAPTCHA_DETECTED"


def test_probe_result_deferred_status():
    r = ProbeResult(source_id="krx_kind", method="playwright", status="DEFERRED")
    assert r.status == "DEFERRED"


# ── New meta fields: cooldown / retry_at / cache_hit / network_log ────────────

def test_probe_result_new_fields_defaults():
    r = ProbeResult(source_id="gt", method="playwright", status="UNKNOWN")
    assert r.cooldown_seconds is None
    assert r.next_retry_at is None
    assert r.retry_after_reason is None
    assert r.cache_hit is False
    assert r.network_log is None


def test_probe_result_rate_limited_with_cooldown():
    r = ProbeResult(
        source_id="google_trends_explore",
        method="playwright",
        status="RATE_LIMITED",
        cooldown_seconds=600,
        next_retry_at="2026-06-08T12:00:00Z",
        retry_after_reason="429_detected_in_rendered_html",
    )
    assert r.status == "RATE_LIMITED"
    assert r.cooldown_seconds == 600
    assert r.next_retry_at == "2026-06-08T12:00:00Z"
    assert r.retry_after_reason == "429_detected_in_rendered_html"


def test_probe_result_cache_hit_flag():
    r = ProbeResult(source_id="gdelt", method="api", status="LIVE_SUCCESS", cache_hit=True)
    assert r.cache_hit is True


def test_probe_result_network_log_field():
    entries = [{"url": "https://kind.krx.co.kr/api", "method": "POST", "status": 200}]
    r = ProbeResult(source_id="krx_kind", method="playwright", status="LIVE_PARTIAL", network_log=entries)
    assert r.network_log == entries


def test_probe_result_to_dict_includes_new_fields():
    r = ProbeResult(
        source_id="google_trends_explore",
        method="playwright",
        status="RATE_LIMITED",
        cooldown_seconds=600,
        next_retry_at="2026-06-08T12:00:00Z",
        retry_after_reason="429_in_html",
        cache_hit=False,
        network_log=[],
    )
    d = r.to_dict()
    assert d["cooldown_seconds"] == 600
    assert d["next_retry_at"] == "2026-06-08T12:00:00Z"
    assert d["retry_after_reason"] == "429_in_html"
    assert d["cache_hit"] is False
    assert d["network_log"] == []
    text = json.dumps(d)
    assert "cooldown_seconds" in text


def test_probe_result_to_dict_none_fields_preserved():
    r = ProbeResult(source_id="x", method="api", status="UNKNOWN")
    d = r.to_dict()
    assert "cooldown_seconds" in d
    assert d["cooldown_seconds"] is None
    assert "next_retry_at" in d
    assert d["cache_hit"] is False
