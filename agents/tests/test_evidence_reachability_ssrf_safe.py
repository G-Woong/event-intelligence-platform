from __future__ import annotations

"""evidence URL HTTP 도달성 검증 — SSRF-safe 단위테스트 (네트워크 0).

fake httpx client + fake DNS resolver 를 주입해 모든 분기를 결정론적으로 검증한다.
"""

import httpx

from agents.nodes.evidence_reachability import check_evidence_reachable

_PUBLIC_IP = "93.184.216.34"


class _FakeResp:
    def __init__(self, status_code: int, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}


class _FakeClient:
    """request(method, url) → 미리 정의한 응답. url 당 리스트면 순차 소비."""

    def __init__(self, routes: dict, raise_on: set | None = None):
        self._routes = {k: (list(v) if isinstance(v, list) else v) for k, v in routes.items()}
        self._raise_on = raise_on or set()
        self.calls: list[tuple[str, str]] = []
        self.request_kwargs: list[dict] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url))
        self.request_kwargs.append(kwargs)
        if url in self._raise_on:
            raise httpx.ConnectError(f"boom {url}")
        r = self._routes.get(url)
        if r is None:
            raise httpx.ConnectError(f"no route {url}")
        if isinstance(r, list):
            return r.pop(0)
        return r


def _public_resolver(host: str) -> list[str]:
    return [_PUBLIC_IP]


# ----- 구조검증 단계 (client 호출 전 차단) -----

def test_localhost_structural_reject():
    c = _FakeClient({})
    res = check_evidence_reachable("http://localhost:8000/x", client=c, resolver=_public_resolver)
    assert res.reachable is False
    assert res.status == "structural_reject"
    assert c.calls == []  # 네트워크 호출 없음


def test_private_ip_literal_structural_reject():
    c = _FakeClient({})
    res = check_evidence_reachable("http://10.0.0.1/x", client=c, resolver=_public_resolver)
    assert res.reachable is False
    assert res.status == "structural_reject"
    assert c.calls == []


def test_non_http_scheme_structural_reject():
    res = check_evidence_reachable("file:///etc/passwd", client=_FakeClient({}), resolver=_public_resolver)
    assert res.status == "structural_reject"


# ----- DNS 해석 후 SSRF 차단 (hostname → 사설/메타데이터 IP) -----

def test_hostname_resolving_to_private_ip_blocked():
    c = _FakeClient({"https://internal.example-corp.io/x": _FakeResp(200)})
    res = check_evidence_reachable(
        "https://internal.example-corp.io/x", client=c, resolver=lambda h: ["10.0.0.5"]
    )
    assert res.reachable is False
    assert res.status == "ssrf_blocked"
    assert c.calls == []  # DNS 단계에서 차단 → HTTP 호출 없음


def test_hostname_resolving_to_metadata_ip_blocked():
    res = check_evidence_reachable(
        "https://evil.example-corp.io/x", client=_FakeClient({}), resolver=lambda h: ["169.254.169.254"]
    )
    assert res.reachable is False
    assert res.status == "ssrf_blocked"
    assert "169.254.169.254" in res.detail


def test_dns_resolution_error_unreachable():
    def _boom(host):
        raise OSError("nxdomain")

    res = check_evidence_reachable("https://nope.invalid-real.io/x", client=_FakeClient({}), resolver=_boom)
    assert res.reachable is False
    assert res.status == "dns_error"


def test_dns_empty_unreachable():
    res = check_evidence_reachable("https://empty.real-host.io/x", client=_FakeClient({}), resolver=lambda h: [])
    assert res.status == "dns_error"


# ----- HTTP 도달성 -----

def test_reachable_head_200():
    url = "https://www.example-news.io/article"
    c = _FakeClient({url: _FakeResp(200)})
    res = check_evidence_reachable(url, client=c, resolver=_public_resolver)
    assert res.reachable is True
    assert res.status == "ok"
    assert res.http_status == 200
    assert c.calls == [("HEAD", url)]


def test_head_405_falls_back_to_get():
    url = "https://www.example-news.io/article"
    c = _FakeClient({url: [_FakeResp(405), _FakeResp(200)]})
    res = check_evidence_reachable(url, client=c, resolver=_public_resolver)
    assert res.reachable is True
    assert c.calls == [("HEAD", url), ("GET", url)]


def test_404_not_reachable():
    url = "https://www.example-news.io/missing"
    c = _FakeClient({url: _FakeResp(404)})
    res = check_evidence_reachable(url, client=c, resolver=_public_resolver)
    assert res.reachable is False
    assert res.status == "http_error"
    assert res.http_status == 404


def test_connect_error_unreachable():
    url = "https://www.example-news.io/article"
    c = _FakeClient({}, raise_on={url})
    res = check_evidence_reachable(url, client=c, resolver=_public_resolver)
    assert res.reachable is False
    assert res.status == "unreachable"


# ----- redirect SSRF 재검증 -----

def test_redirect_to_public_followed():
    a = "https://a.example-news.io/x"
    b = "https://b.example-news.io/y"
    c = _FakeClient({a: _FakeResp(302, {"location": b}), b: _FakeResp(200)})
    res = check_evidence_reachable(a, client=c, resolver=_public_resolver)
    assert res.reachable is True
    assert res.url == b
    assert c.calls == [("HEAD", a), ("HEAD", b)]


def test_redirect_to_private_ip_blocked():
    a = "https://a.example-news.io/x"
    c = _FakeClient({a: _FakeResp(302, {"location": "http://10.0.0.9/internal"})})
    res = check_evidence_reachable(a, client=c, resolver=_public_resolver)
    assert res.reachable is False
    assert res.status == "ssrf_blocked"


def test_redirect_to_private_hostname_blocked_at_dns():
    a = "https://a.example-news.io/x"
    bad = "https://intranet.example-news.io/secret"
    c = _FakeClient({a: _FakeResp(302, {"location": bad}), bad: _FakeResp(200)})

    def _resolver(host: str) -> list[str]:
        return ["10.1.2.3"] if host.startswith("intranet") else [_PUBLIC_IP]

    res = check_evidence_reachable(a, client=c, resolver=_resolver)
    assert res.reachable is False
    assert res.status == "ssrf_blocked"


def test_too_many_redirects():
    a = "https://a.example-news.io/x"
    b = "https://b.example-news.io/y"
    c = _FakeClient({a: _FakeResp(302, {"location": b}), b: _FakeResp(302, {"location": a})})
    res = check_evidence_reachable(a, client=c, resolver=_public_resolver, max_redirects=2)
    assert res.reachable is False
    assert res.status == "too_many_redirects"


def test_redirect_without_location_is_http_error():
    a = "https://a.example-news.io/x"
    c = _FakeClient({a: _FakeResp(302, {})})
    res = check_evidence_reachable(a, client=c, resolver=_public_resolver)
    assert res.reachable is False
    assert res.status == "http_error"


# ----- 적대적 리뷰 회귀 잠금: IPv4-mapped IPv6 + follow_redirects 강제 -----

def test_ipv4_mapped_metadata_literal_structural_reject():
    # http://[::ffff:169.254.169.254]/ — IPv4-mapped IPv6로 메타데이터 우회 시도 차단(구조검증).
    from agents.nodes.evidence_rules import is_valid_evidence_url, ip_is_public

    assert is_valid_evidence_url("http://[::ffff:169.254.169.254]/latest/meta-data/") is False
    assert is_valid_evidence_url("http://[::ffff:127.0.0.1]/x") is False
    assert ip_is_public("::ffff:169.254.169.254") is False
    assert ip_is_public("::ffff:10.0.0.1") is False
    assert ip_is_public("::1") is False
    # 공개 IPv4-mapped / 공개 IPv4 / 공개 IPv6는 허용
    assert ip_is_public("::ffff:8.8.8.8") is True
    assert ip_is_public("8.8.8.8") is True


def test_ipv4_mapped_via_resolver_blocked():
    # DNS가 IPv4-mapped 메타데이터 IP를 반환해도 차단.
    res = check_evidence_reachable(
        "https://host.real-news.io/x", client=_FakeClient({}), resolver=lambda h: ["::ffff:169.254.169.254"]
    )
    assert res.reachable is False
    assert res.status == "ssrf_blocked"


def test_request_forces_follow_redirects_false():
    # 주입 client 가 자동추적 설정이어도 per-request follow_redirects=False 가 강제되는지.
    url = "https://www.real-news.io/article"
    c = _FakeClient({url: _FakeResp(200)})
    check_evidence_reachable(url, client=c, resolver=_public_resolver)
    assert c.request_kwargs and c.request_kwargs[0].get("follow_redirects") is False
