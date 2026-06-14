"""canonical_url no-network 정규화 (Phase D-4, 설계 04 §4).

기본은 **네트워크 호출 0**. 주어진 기사 URL 문자열을 표준화하는 순수 함수다:
scheme/host 소문자화, 기본 포트 제거, fragment 제거, tracking query 제거,
trailing slash 정책 적용. 같은 기사를 가리키는 URL의 표기 차이를 줄여(dedup) 다운스트림
content_hash 충돌을 방지한다.

네트워크 redirect 해석(Google News 신형 URL → 원본 복원 등)은 ``ingestion/tools/url_resolver``
가 담당하며 **기본 off**다. ``allow_network_resolution=True`` + ``resolver`` 주입이 모두
있을 때만 호출한다 — rate/quota gate 밖에서 임의 네트워크 호출을 하지 않기 위함이다.
"""
from __future__ import annotations

from typing import Callable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 추적 파라미터(클릭 출처/캠페인 식별자) — 기사 식별과 무관하므로 제거한다.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_EXACT = frozenset({
    "gclid", "fbclid", "igshid", "mc_eid", "mc_cid", "ref", "ref_src",
    "spm", "cmpid", "ncid", "_hsenc", "_hsmi", "vero_id", "mkt_tok",
    "yclid", "dclid", "gclsrc", "wt_mc", "s_cid",
})
_DEFAULT_PORTS = {"http": "80", "https": "443"}


def _is_tracking_param(key: str) -> bool:
    k = key.lower()
    if k in _TRACKING_EXACT:
        return True
    return any(k.startswith(p) for p in _TRACKING_PREFIXES)


def canonicalize_url(
    url: Optional[str],
    *,
    allow_network_resolution: bool = False,
    resolver: Optional[Callable[[str], str]] = None,
) -> Optional[str]:
    """기사 URL을 no-network로 정규화한다. 정규화 불가 시 ``None``.

    정책(없는 사실을 만들지 않는다):
    - ``None``/빈 문자열/공백 → ``None``.
    - scheme이 http/https가 아니거나 host가 없으면 정규화 불가 → ``None``(원문 보존 안 함).
    - scheme/host 소문자화, host의 기본 포트(80/443) 제거. path는 대소문자 보존(경로는 민감).
    - fragment(``#...``) 제거.
    - tracking query 제거 후 남은 query는 키 기준 정렬(표기 안정화). 남은 게 없으면 query 제거.
    - trailing slash: 루트("/")는 유지, 그 외 경로의 끝 슬래시는 제거.

    네트워크: ``allow_network_resolution=True`` **이고** ``resolver``가 주어질 때만 resolver를
    호출해 redirect를 해석하고, 그 결과를 다시 no-network 정규화한다. 그 외에는 절대 네트워크를
    건드리지 않는다(기본).
    """
    if not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw:
        return None

    normalized = _normalize_no_network(raw)
    if normalized is None:
        return None

    if allow_network_resolution and resolver is not None:
        try:
            resolved = resolver(normalized)
        except Exception:
            resolved = normalized
        # resolver 결과도 동일 규칙으로 정규화. 실패 시 직전 값 유지.
        renorm = _normalize_no_network(resolved) if resolved else None
        return renorm or normalized

    return normalized


def _normalize_no_network(raw: str) -> Optional[str]:
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        return None

    host = parts.hostname.lower()
    netloc = host
    # userinfo 보존
    if parts.username is not None:
        cred = parts.username
        if parts.password is not None:
            cred = f"{cred}:{parts.password}"
        netloc = f"{cred}@{netloc}"
    # 기본 포트 제거, 비표준 포트는 보존
    if parts.port is not None and str(parts.port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{netloc}:{parts.port}"

    path = parts.path
    if path and path != "/":
        path = path.rstrip("/")

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _is_tracking_param(k)]
    query = urlencode(sorted(kept)) if kept else ""

    return urlunsplit((scheme, netloc, path, query, ""))
