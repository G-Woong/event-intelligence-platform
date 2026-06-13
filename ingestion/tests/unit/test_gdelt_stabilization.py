"""gdelt 안정화(02 문서) 단위 테스트 — 전부 네트워크 없음.

비-JSON 200 재분류 테스트는 01 문서의 _FakeResponse/_FakeClient/_patch_httpx를
재사용한다 (같은 규칙 두 벌 금지).
"""
import os

os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "memory")

import pytest

from ingestion.tests.unit.test_route1_rate_limit_record import (
    _FakeResponse,
    _patch_httpx,
)


@pytest.fixture(autouse=True)
def _fresh_stores(monkeypatch):
    from ingestion.core import rate_limit_store
    from ingestion.core.rate_limit_policy import _call_cache
    rate_limit_store.reset_store_for_tests()
    _call_cache.clear()
    yield
    rate_limit_store.reset_store_for_tests()


# ── §3-a phrase quoting ──────────────────────────────────────────────────────

def test_quote_phrase_wraps_multiword():
    from ingestion.probes.api_probe import _transform_query
    assert _transform_query("have duty to stay on", "quote_phrase") == '"have duty to stay on"'
    assert _transform_query("samsung", "quote_phrase") == "samsung"           # 단어 1개는 그대로
    assert _transform_query('"already quoted"', "quote_phrase") == '"already quoted"'  # 이중 인용 방지


def test_apply_query_override_uses_transform():
    from ingestion.probes.api_probe import _PROBE_SPEC, _apply_query_override
    spec = _apply_query_override(_PROBE_SPEC["gdelt"], "global conflict")
    assert spec["extra_params"]["query"] == '"global conflict"'
    # 전역 불변 (deepcopy 회귀 방지)
    assert _PROBE_SPEC["gdelt"]["extra_params"]["query"] == "samsung"


# ── §3-b 비-JSON 200 응답 정직 분류 ──────────────────────────────────────────

def test_non_json_rate_limit_text_reclassified(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    _patch_httpx(monkeypatch, _FakeResponse(
        status_code=200, text="You have exceeded the rate limit. Too many requests.",
        json_data=None,
    ))
    result = run_api_live_probe("gdelt", max_calls=1, query="global conflict")
    assert result.status == "RATE_LIMITED"
    # 01의 record 블록이 cooldown까지 기록해야 한다
    assert result.next_retry_at is not None


def test_gdelt_soft_limit_plaintext_reclassified(monkeypatch):
    # 실측 raw payload: GDELT가 soft limit을 200+평문으로 알린 경우
    from ingestion.probes.api_probe import run_api_live_probe
    _patch_httpx(monkeypatch, _FakeResponse(
        status_code=200,
        text="Please limit requests to one every 5 seconds or contact ... for larger queries.",
        json_data=None,
    ))
    result = run_api_live_probe("gdelt", max_calls=1, query="global conflict")
    assert result.status == "RATE_LIMITED"
    assert result.next_retry_at is not None


def test_non_json_query_error_text_reclassified(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    _patch_httpx(monkeypatch, _FakeResponse(
        status_code=200, text="Your query was too short or too long.",
        json_data=None,
    ))
    result = run_api_live_probe("gdelt", max_calls=1, query="x")
    assert result.status == "QUERY_ENCODING_OR_PARAM_ERROR"


# ── §3-d 장문 query 절단 ─────────────────────────────────────────────────────

def test_truncate_query():
    from ingestion.runners._audit_common import truncate_query
    long_q = "일괄신고서 (집합투자증권-신탁형) 제출 관련 안내 공시 자료 추가 첨부"
    out = truncate_query(long_q)
    assert len(out) <= 60 and len(out.split()) <= 5
    assert "(" not in out
