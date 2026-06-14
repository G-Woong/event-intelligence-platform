"""Phase D-4: canonical_url no-network 정규화."""
from __future__ import annotations

from ingestion.orchestration.canonical_url import canonicalize_url


def test_utm_and_tracking_params_removed():
    out = canonicalize_url("https://news.test/a?utm_source=x&utm_medium=rss&id=7&gclid=z")
    assert out == "https://news.test/a?id=7"


def test_fragment_removed():
    assert canonicalize_url("https://news.test/a#section-2") == "https://news.test/a"


def test_host_and_scheme_lowercased_default_port_stripped():
    out = canonicalize_url("HTTPS://News.TEST:443/Path/Sub/")
    # host/scheme 소문자, 기본 포트 제거, trailing slash 제거, path 대소문자 보존
    assert out == "https://news.test/Path/Sub"


def test_root_path_slash_preserved():
    assert canonicalize_url("https://news.test/") == "https://news.test/"


def test_remaining_query_sorted_for_stability():
    a = canonicalize_url("https://news.test/a?b=2&a=1")
    b = canonicalize_url("https://news.test/a?a=1&b=2")
    assert a == b == "https://news.test/a?a=1&b=2"


def test_none_and_empty_return_none():
    assert canonicalize_url(None) is None
    assert canonicalize_url("") is None
    assert canonicalize_url("   ") is None


def test_malformed_or_non_http_returns_none():
    # 정규화 불가 → 원문 보존 안 함, None (정책 명확화)
    assert canonicalize_url("not a url") is None
    assert canonicalize_url("ftp://files.test/a") is None
    assert canonicalize_url("mailto:a@b.test") is None
    assert canonicalize_url("//news.test/a") is None


def test_no_network_call_by_default(monkeypatch):
    """기본 경로는 절대 네트워크 resolver를 호출하지 않는다."""
    calls = []

    def boom(url):
        calls.append(url)
        return url

    # resolver를 줘도 allow_network_resolution=False(기본)면 호출 안 됨
    canonicalize_url("https://news.test/a", resolver=boom)
    assert calls == []


def test_network_resolution_only_when_explicitly_enabled():
    seen = []

    def fake_resolver(url):
        seen.append(url)
        return "https://resolved.test/final?utm_source=x"

    out = canonicalize_url(
        "https://news.google.com/rss/articles/ABC",
        allow_network_resolution=True,
        resolver=fake_resolver,
    )
    assert seen  # 명시적으로 켰을 때만 호출
    assert out == "https://resolved.test/final"  # 결과도 재정규화됨


def test_canonicalization_is_idempotent():
    once = canonicalize_url("HTTPS://News.TEST:443/a/?utm_source=x&b=2&a=1#f")
    twice = canonicalize_url(once)
    assert once == twice  # dedup 핵심 속성


def test_userinfo_and_nonstandard_port_preserved():
    out = canonicalize_url("https://user:pw@News.TEST:8443/Path/")
    assert out == "https://user:pw@news.test:8443/Path"


def test_resolver_exception_falls_back_to_no_network_value():
    def boom(url):
        raise RuntimeError("resolver down")

    out = canonicalize_url(
        "https://news.test/a?utm_source=x",
        allow_network_resolution=True, resolver=boom,
    )
    # resolver가 죽어도 no-network 정규화 값은 유지(사건 손실 없음)
    assert out == "https://news.test/a"
