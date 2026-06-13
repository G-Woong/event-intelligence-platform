"""RISK-T04: Route 1 429 → record_rate_limited + next_retry_at (docs/90 §3, 01 문서).

전부 네트워크 없음 — httpx.Client를 monkeypatch한 fake client를 쓴다.
"""
import os

os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "memory")

import pytest


class _FakeResponse:
    def __init__(self, status_code=429, text="rate limited", headers=None, json_data=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


class _FakeClient:
    def __init__(self, response, **kwargs):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, *a, **k):
        return self._response

    def post(self, *a, **k):
        return self._response


@pytest.fixture(autouse=True)
def _fresh_stores(monkeypatch):
    from ingestion.core import rate_limit_store
    from ingestion.core.rate_limit_policy import _call_cache
    rate_limit_store.reset_store_for_tests()
    _call_cache.clear()
    yield
    rate_limit_store.reset_store_for_tests()


def _patch_httpx(monkeypatch, response):
    import httpx
    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeClient(response, **kw))


def test_http_429_records_cooldown_and_next_retry(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from ingestion.core.rate_limit_policy import in_cooldown
    _patch_httpx(monkeypatch, _FakeResponse(status_code=429))
    # gdelt: 키 불필요 public API — MISSING_KEY 분기를 타지 않음
    result = run_api_live_probe("gdelt", max_calls=1)
    assert result.status == "RATE_LIMITED"
    assert result.next_retry_at, "next_retry_at must be set on 429"
    cooled, at = in_cooldown("gdelt", "")
    assert cooled and at == result.next_retry_at


def test_429_with_query_records_query_scoped_key(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from ingestion.core.rate_limit_policy import in_cooldown
    _patch_httpx(monkeypatch, _FakeResponse(status_code=429))
    result = run_api_live_probe("gdelt", max_calls=1, query="global conflict")
    assert result.status == "RATE_LIMITED"
    assert in_cooldown("gdelt", "global conflict")[0]


def test_retry_after_header_extends_cooldown(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from datetime import datetime, timezone
    _patch_httpx(monkeypatch, _FakeResponse(status_code=429, headers={"Retry-After": "3600"}))
    result = run_api_live_probe("gdelt", max_calls=1)
    deadline = datetime.fromisoformat(result.next_retry_at.replace("Z", "+00:00"))
    # gdelt 정책 cooldown(300~900s)보다 길어야 한다
    assert (deadline - datetime.now(timezone.utc)).total_seconds() > 3000


def test_alpha_vantage_soft_limit_records_cooldown(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from ingestion.core.rate_limit_policy import in_cooldown
    # alpha_vantage는 키 필요 — 가짜 키 주입 (값은 테스트 전용 더미)
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-dummy-key-not-real")
    _patch_httpx(monkeypatch, _FakeResponse(
        status_code=200, text='{"Note": "limit"}', json_data={"Note": "limit"}
    ))
    result = run_api_live_probe("alpha_vantage", max_calls=1)
    assert result.status == "RATE_LIMITED"
    assert result.next_retry_at
    assert in_cooldown("alpha_vantage", "")[0]


def test_success_does_not_record_cooldown(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from ingestion.core.rate_limit_policy import in_cooldown
    _patch_httpx(monkeypatch, _FakeResponse(
        status_code=200, text='{"articles": []}', json_data={"articles": []}
    ))
    result = run_api_live_probe("gdelt", max_calls=1)
    assert result.status in ("LIVE_SUCCESS", "LIVE_PARTIAL")
    assert result.next_retry_at is None
    assert not in_cooldown("gdelt", "")[0]
