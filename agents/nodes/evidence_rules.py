from __future__ import annotations

"""evidence 근거 URL 판정 규칙 (단일 출처).

P0 하드닝: mock/합성/로컬 마커를 "검증된 근거"로 취급하지 않기 위해 evidence_check 와
publish_or_hold 가 공유하는 결정론적 판정. ingestion 패키지에 의존하지 않는다(agents 이미지 독립).

판정은 구조적 유효성만 본다(스킴/호스트/합성마커). 실제 도달성(HTTP 200) 검증은 네트워크가
필요하므로 별도 단계로 남긴다(T-AgtA evidence reachability).
"""

import ipaddress
from urllib.parse import urlparse

# 합성/로컬/플레이스홀더 근거를 published 근거로 인정하지 않는다.
_SYNTHETIC_MARKERS = (
    "mock",
    "synthetic",
    "placeholder",
    "localhost",
)
# RFC2606/RFC6761 예약 도메인·TLD는 문서/예시용 — 검증된 근거로 인정 금지.
_RESERVED_HOSTS = ("example.com", "example.org", "example.net")
_RESERVED_HOST_SUFFIXES = (".test", ".invalid", ".localhost", ".example")


def _host_is_disallowed_ip(host: str) -> bool:
    """사설/loopback/link-local(메타데이터 169.254.169.254)/예약 IP면 근거 부적격."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # 호스트명(IP 아님)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_valid_evidence_url(value: object) -> bool:
    """http(s) + 공개 호스트이고 합성/예약/사설 마커가 없는 URL만 유효 근거로 인정.

    구조적 유효성 + 공개성까지만 본다. 실제 도달성(HTTP 200)·출처 신뢰도는 별도 단계(T-AgtA).
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    low = candidate.lower()
    if any(marker in low for marker in _SYNTHETIC_MARKERS):
        return False
    if low.startswith("[") or low.startswith("<"):
        # "[mock-source-1]" 같은 플레이스홀더 토큰
        return False
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname  # 포트/대괄호 제거 + 소문자
    if not host:
        return False
    if host in _RESERVED_HOSTS:
        return False
    if any(host.endswith(suffix) for suffix in _RESERVED_HOST_SUFFIXES):
        return False
    if _host_is_disallowed_ip(host):
        return False
    return True


def has_grounded_evidence(evidence: object) -> bool:
    """evidence 리스트에 유효 근거 URL이 하나 이상 있는지."""
    if not isinstance(evidence, (list, tuple)):
        return False
    return any(is_valid_evidence_url(item) for item in evidence)
