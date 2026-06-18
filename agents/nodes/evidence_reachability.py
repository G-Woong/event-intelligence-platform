from __future__ import annotations

"""evidence URL HTTP 도달성 검증 (best-effort SSRF 완화).

`is_valid_evidence_url` 의 구조검증(스킴 allowlist·합성마커·IP 리터럴 SSRF)을 통과한 URL에 한해
실제 HTTP 도달성을 확인한다. 네트워크가 필요하므로 `settings.EVIDENCE_REACHABILITY_CHECK` 가
켜졌을 때만 evidence_check 가 호출한다(기본 off → 단위테스트/오프라인 흐름 무변경).

SSRF 완화(구조검증 위에 추가):
  - DNS 해석 후 모든 결과 IP가 전역 유니캐스트(`ip_is_public`/is_global)인지 검증
    (hostname → 사설/메타데이터/공유 IP SSRF 차단).
  - redirect 를 자동 추적하지 않고(매 요청 follow_redirects=False 강제) 매 hop 구조검증 + DNS 재검증
    (open redirect 를 통한 SSRF 차단).
  - 짧은 timeout, redirect 횟수 상한, HEAD 우선 → 거부 시 GET fallback.

⚠ 잔존 위험(미해결, 의도적): DNS rebinding/TOCTOU — 위 DNS 검증과 httpx 의 실제 connect 시
재해석 사이에 IP 가 바뀔 수 있다(완전한 SSRF-safe 아님). 신뢰 못 할 도메인에서 이 플래그를
켤 때는 egress 방화벽으로 사설/메타데이터 대역을 별도 차단할 것. 기본 off 인 이유.

도달 실패는 예외를 던지지 않고 reachable=False 로 환원한다(downstream publish_or_hold 가 hold).
"""

import socket
from dataclasses import dataclass
from typing import Callable, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from agents.nodes.evidence_rules import ip_is_public, is_valid_evidence_url

# host -> resolved IP 문자열 리스트. 테스트에서 주입 가능(네트워크 0).
Resolver = Callable[[str], List[str]]

_REDIRECT_CODES = (301, 302, 303, 307, 308)
# HEAD 를 거부/미지원하는 서버 → 동일 URL 을 GET 으로 한 번 재시도.
_HEAD_UNSUPPORTED_CODES = (403, 405, 501)


@dataclass(frozen=True)
class ReachabilityResult:
    """도달성 판정 결과(LLM/agent trace 용 status/detail 포함)."""

    url: str
    reachable: bool
    status: str  # ok | structural_reject | ssrf_blocked | dns_error | http_error | unreachable | too_many_redirects
    detail: str = ""
    http_status: Optional[int] = None


def _default_resolver(host: str) -> List[str]:
    infos = socket.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


def _resolved_host_is_safe(host: str, resolver: Resolver) -> tuple[bool, str]:
    """host 의 모든 DNS 결과 IP 가 공개 IP면 (True, "")."""
    if not host:
        return False, "dns_error:no_host"
    try:
        ips = resolver(host)
    except Exception as exc:  # noqa: BLE001 - DNS 실패는 도달불가로 환원
        return False, f"dns_error:{type(exc).__name__}"
    if not ips:
        return False, "dns_error:empty"
    for ip in ips:
        if not ip_is_public(ip):
            return False, f"ssrf_blocked:{ip}"
    return True, ""


def check_evidence_reachable(
    url: str,
    *,
    client: Optional[httpx.Client] = None,
    resolver: Resolver = _default_resolver,
    timeout_sec: float = 5.0,
    max_redirects: int = 3,
) -> ReachabilityResult:
    """url 이 SSRF-safe 하게 실제로 도달 가능한지(status < 400) 판정한다.

    client 미주입 시 httpx.Client 를 생성/정리한다. redirect 는 자동 추적하지 않고(`follow_redirects`
    off) 매 hop 을 직접 재검증한다.
    """
    if not is_valid_evidence_url(url):
        return ReachabilityResult(url, False, "structural_reject", "is_valid_evidence_url=False")

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=timeout_sec, follow_redirects=False)
    try:
        current = url
        method = "HEAD"
        redirects = 0
        while True:
            host = urlparse(current).hostname or ""
            safe, reason = _resolved_host_is_safe(host, resolver)
            if not safe:
                kind = "ssrf_blocked" if reason.startswith("ssrf") else "dns_error"
                return ReachabilityResult(current, False, kind, reason)

            try:
                # follow_redirects=False 를 매 요청에 강제 — 주입 client 가 자동추적 설정이어도
                # per-hop 재검증 불변식을 깨지 못하게 한다.
                resp = client.request(method, current, follow_redirects=False)
            except httpx.HTTPError as exc:
                return ReachabilityResult(current, False, "unreachable", type(exc).__name__)

            code = resp.status_code

            if code in _REDIRECT_CODES:
                location = resp.headers.get("location")
                if not location:
                    return ReachabilityResult(current, False, "http_error", "redirect_no_location", code)
                nxt = urljoin(current, location)
                # open redirect 를 통한 SSRF/우회 차단: 다음 hop 도 구조검증 통과해야 한다.
                if not is_valid_evidence_url(nxt):
                    return ReachabilityResult(nxt, False, "ssrf_blocked", "redirect_target_invalid", code)
                redirects += 1
                if redirects > max_redirects:
                    return ReachabilityResult(current, False, "too_many_redirects", f">{max_redirects}", code)
                current = nxt
                method = "HEAD"
                continue

            if method == "HEAD" and code in _HEAD_UNSUPPORTED_CODES:
                method = "GET"
                continue

            if code < 400:
                return ReachabilityResult(current, True, "ok", method, code)
            return ReachabilityResult(current, False, "http_error", f"status={code}", code)
    finally:
        if owns_client:
            client.close()
