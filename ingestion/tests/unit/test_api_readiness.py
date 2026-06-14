"""Phase D-0: API key readiness audit. 키 값은 절대 노출하지 않는다.

env는 monkeypatch로만 다루고, 실제 .env 값은 fixture에 넣지 않는다. env_path를 빈 임시
파일로 고정해 실제 .env 재로딩을 차단하고 os.environ만 제어한다.
"""
from __future__ import annotations

import pytest

from ingestion.orchestration.api_readiness import (
    audit_api_key_readiness,
    summarize_readiness,
)
from ingestion.orchestration.source_profile import SourceProfile

_SENTINEL = "SENTINEL_SECRET_VALUE_DO_NOT_PRINT_123"


@pytest.fixture
def empty_env(tmp_path):
    p = tmp_path / ".env"
    p.write_text("", encoding="utf-8")
    return p


def _profile(source_id, **kw):
    kw.setdefault("requires_api_key", True)
    return SourceProfile(source_id=source_id, **kw)


def test_required_key_present_is_ready(monkeypatch, empty_env):
    monkeypatch.setenv("FINNHUB_API_KEY", _SENTINEL)
    r = audit_api_key_readiness([_profile("finnhub")], env_path=empty_env)[0]
    assert r.readiness_status == "ready"
    assert r.keys_present is True
    assert r.missing_keys == ()
    assert r.safe_to_live_smoke is True


def test_required_key_missing(monkeypatch, empty_env):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    r = audit_api_key_readiness([_profile("finnhub")], env_path=empty_env)[0]
    assert r.readiness_status == "missing"
    assert r.keys_present is False
    assert "FINNHUB_API_KEY" in r.missing_keys
    assert r.safe_to_live_smoke is False


def test_alias_mismatch_is_ambiguous(monkeypatch, empty_env):
    # bok_ecos는 BOK_ECOS_API_KEY를 요구하나 .env는 alias ECOS_API_KEY를 쓸 수 있다
    monkeypatch.delenv("BOK_ECOS_API_KEY", raising=False)
    monkeypatch.setenv("ECOS_API_KEY", _SENTINEL)
    r = audit_api_key_readiness([_profile("bok_ecos")], env_path=empty_env)[0]
    assert r.readiness_status == "ambiguous"
    assert r.keys_present is True
    assert any("BOK_ECOS_API_KEY<-ECOS_API_KEY" == w for w in r.alias_warning)


def test_no_key_required_is_not_required(empty_env):
    r = audit_api_key_readiness(
        [SourceProfile(source_id="bbc", requires_api_key=False)], env_path=empty_env
    )[0]
    assert r.readiness_status == "not_required"
    assert r.required_keys == ()
    assert r.safe_to_live_smoke is True


def test_unregistered_required_source_is_unknown(empty_env):
    r = audit_api_key_readiness(
        [SourceProfile(source_id="nonexistent_src", requires_api_key=True)],
        env_path=empty_env,
    )[0]
    assert r.readiness_status == "unknown"
    assert r.safe_to_live_smoke is False


def test_policy_blocked_not_safe_even_without_key(empty_env):
    p = SourceProfile(
        source_id="reuters", requires_api_key=False, enabled=False,
        profile_status="blocked_policy", skip_reason="paywall_no_bypass",
    )
    r = audit_api_key_readiness([p], env_path=empty_env)[0]
    assert r.readiness_status == "not_required"
    assert r.safe_to_live_smoke is False  # 정책 차단은 키 무관하게 unsafe


def test_secret_value_never_appears_in_output(monkeypatch, empty_env):
    monkeypatch.setenv("FINNHUB_API_KEY", _SENTINEL)
    results = audit_api_key_readiness([_profile("finnhub")], env_path=empty_env)
    blob = repr(results) + str(summarize_readiness(results))
    assert _SENTINEL not in blob


def test_summary_counts(monkeypatch, empty_env):
    monkeypatch.setenv("FINNHUB_API_KEY", _SENTINEL)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    profiles = [
        _profile("finnhub"),
        _profile("tavily"),
        SourceProfile(source_id="bbc", requires_api_key=False),
    ]
    summary = summarize_readiness(audit_api_key_readiness(profiles, env_path=empty_env))
    assert summary["ready"] >= 1
    assert summary["missing"] >= 1
    assert summary["not_required"] >= 1
