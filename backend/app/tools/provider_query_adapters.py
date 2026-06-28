"""ADR#62 — provider query adapter contract + first wired key-required adapter (Guardian).

ADR#61 이 정직하게 남긴 병목: query-capable provider 10종이 registry/credential/host-gate 까지 분류되나 **실
fetcher 는 gdelt/rss 만 배선**(나머지는 fetcher_not_wired). 이 모듈은 그 병목을 한 단계 줄인다 —
  ① query-capable provider fetch 가 따라야 할 **공통 contract**(ProviderQueryAdapter / ProviderQueryResult)를
     명시하고(옵션 A),
  ② 그 contract 에 맞는 **첫 실 adapter**(Guardian Content API · key-required · news)를 wire 한다(옵션 B).
자동 병합 턴도, LLM 본경로 턴도, 운영 DB 배포 턴도 아니다. 산출 records 는 ADR#60 운영 경로(discover→near-match
reviewer/gold queue)로만 연결된다(옵션 D) — 같은 사건 단정·병합은 gold/MERGE_GATE 전까지 0.

경계(불변·상속 — 상용 안전 계약):
  - **no raw body**: title(≤512)+canonical_url+published_at 만(`_rec` body 필드 없음). 전문/raw_payload/PII 미저장.
  - **secret 값 0**: credential 은 `env_status`(present/missing·**값 미반환**)로만 확인. API key 값은 실 network
    (transport=None) 경로에서만 `os.getenv` 로 읽어 요청 URL 구성에 쓰고 **로그·result·report 미기록**
    (ProviderQueryResult.secret_exposed=False 단언·fake transport 경로는 key 없이 동작).
  - **no DB write·no merge·no LLM·no public IU**: adapter 는 fetch+normalize 만. discover/queue/gold 는 ADR#57/#59/#60.
  - **governed(no-bypass)**: shared `HostRateGate` 참여(host floor)·`rate_limit_policy`(in_cooldown/record_rate_limited)·
    `error_taxonomy` 재사용·RATE_LIMITED 는 tight retry 안 함(cooldown 만료 후 재시도).
  - **fixture 둔갑 금지**: 실 fetch 가 0/실패면 status+block_reason 으로 정직 노출(synthetic 으로 떨어지지 않음).
    fake transport(test) 경로는 결정론이나 **실 parser 를 그대로 통과**한다(skeleton 아님 — 공식 응답 shape 파싱).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlencode

# `_rec`(정규화 record 단일 출처) / `_BROWSER_UA`(공통 UA) 재사용 — 재구현 0.
from backend.app.tools.source_overlap_discovery import _BROWSER_UA, _rec

ADAPTER_CONTRACT_VERSION = "1.0"
_DEFAULT_MAX_RECORDS = 25   # bounded(폭주·rate-limit 차단).

# ── ProviderQueryResult.status 어휘(§5 계약) ───────────────────────────────────────────────────────────
ST_OK = "ok"
ST_MISSING_CREDENTIALS = "missing_credentials"
ST_RATE_LIMITED = "rate_limited"
ST_HOST_GATE_BLOCKED = "host_gate_blocked"
ST_FETCHER_NOT_WIRED = "fetcher_not_wired"
ST_NETWORK_ERROR = "network_error"
ST_PARSER_ERROR = "parser_error"
ST_NO_RECORDS = "no_records"
ST_DISABLED = "disabled"
ST_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderQueryResult:
    """provider adapter fetch 결과(§5 계약). records 는 `_rec`-shape(본문 미저장). secret/raw body 노출 0 불변."""
    provider_id: str
    status: str
    records: list[dict] = field(default_factory=list)
    records_count: int = 0
    raw_body_stored: bool = False     # 불변 False — title+canonical 만 보존.
    secret_exposed: bool = False      # 불변 False — key 값은 result/log 미기록.
    provenance: str = "none"          # status==ok 일 때만 "live_derived".
    block_reason: Optional[str] = None
    next_action: Optional[str] = None


@dataclass(frozen=True)
class ProviderQueryAdapter:
    """query-capable provider fetch 가 따라야 할 공통 contract 기술(메타데이터·secret 0)."""
    provider_id: str
    query_capable: bool
    auth_required: bool
    required_env_vars: tuple[str, ...]
    fetch_implemented: bool
    supports_topic_query: bool
    supports_time_window: bool
    supports_source_pair: bool
    max_records: int
    rate_limit_policy_id: str
    host: str
    host_gate_key: Optional[str]
    host_min_spacing_seconds: int


# ── 첫 실 adapter: Guardian Content API(key-required·news·topic+time_window·평탄 안정 JSON) ───────────────
# robots/tos: 무료 tier 비상업·full content 재배포 금지(_SERVICE_CONFIGS note). 본 adapter 는 title+canonical_url
# +published_at 만 near-match 탐지용으로 쓰고 **본문 미저장·public IU 미생성** → 재배포 아님(ToS 경계 내).
_GUARDIAN_HOST = "content.guardianapis.com"
_GUARDIAN_HOST_MIN_SPACING_SECONDS = 5   # 보수적 shared-gate floor(no-bypass·free tier 5000/day 대비 여유).

GUARDIAN_ADAPTER = ProviderQueryAdapter(
    provider_id="guardian", query_capable=True, auth_required=True,
    required_env_vars=("GUARDIAN_API_KEY",), fetch_implemented=True,
    supports_topic_query=True, supports_time_window=True, supports_source_pair=False,
    max_records=_DEFAULT_MAX_RECORDS, rate_limit_policy_id="guardian",
    host=_GUARDIAN_HOST, host_gate_key=_GUARDIAN_HOST,
    host_min_spacing_seconds=_GUARDIAN_HOST_MIN_SPACING_SECONDS,
)

# ── 2nd 실 adapter: NYT Article Search API(ADR#64·key-required·news·topic+time_window) ──────────────────
# ADR#63 가 실 key 로 입증한 한계: Guardian 단일 source same-event overlap 0(no_title_overlap·구조적). 다음 unblock
# 은 cross-source — Guardian 과 같은 영문 quality **단일 publisher** 를 붙여 다출처 같은 사건 near-match 를 만든다
# (aggregator(newsapi/gnews)는 Guardian 자기기사 재유입=same-source 오염 위험 → 단일 publisher NYT 가 깨끗). NYT 는
# auth=query_param `api-key`(Guardian 과 동일) → run_provider_query 의 params 전달 **무수정 재사용**. robots/tos: 무료
# 500/day·비상업(별도 라이선스 시 상업)·본 adapter 는 headline+web_url+pub_date 만 near-match 탐지용으로 쓰고 **본문
# 미저장·public IU 미생성** → 재배포 아님(Guardian 과 동일 ToS 경계). date 형식만 YYYYMMDD(_nyt_url 가 변환).
_NYT_HOST = "api.nytimes.com"
_NYT_HOST_MIN_SPACING_SECONDS = 12   # NYT 5 req/min 권고 → 12s shared-gate floor(no-bypass·free 500/day 보수).

NYT_ADAPTER = ProviderQueryAdapter(
    provider_id="nyt", query_capable=True, auth_required=True,
    required_env_vars=("NYT_API_KEY",), fetch_implemented=True,
    supports_topic_query=True, supports_time_window=True, supports_source_pair=False,
    max_records=_DEFAULT_MAX_RECORDS, rate_limit_policy_id="nyt",
    host=_NYT_HOST, host_gate_key=_NYT_HOST,
    host_min_spacing_seconds=_NYT_HOST_MIN_SPACING_SECONDS,
)

_ADAPTERS: dict[str, ProviderQueryAdapter] = {"guardian": GUARDIAN_ADAPTER, "nyt": NYT_ADAPTER}
# 이 모듈의 contract adapter 로 fetch 되는 provider(= ADR#60 native gdelt/rss 가 **아닌** 신규 wired provider).
ADAPTER_WIRED_PROVIDERS = frozenset(_ADAPTERS)


# ── governance 단일 출처 재사용(defensive import·실패해도 fail-closed/no-op) ────────────────────────────
def _default_env_status(keys: list[str]) -> dict[str, str]:
    if not keys:
        return {}
    try:
        from ingestion.core.env_loader import env_status
        return env_status(list(keys))
    except Exception:
        return {k: "missing" for k in keys}


def _in_cooldown(policy_id: str, query: str) -> tuple[bool, Optional[str]]:
    try:
        from ingestion.core.rate_limit_policy import in_cooldown
        return in_cooldown(policy_id, query)
    except Exception:
        return (False, None)


def _record_rate_limited(policy_id: str, query: str) -> None:
    try:
        from ingestion.core.rate_limit_policy import record_rate_limited
        record_rate_limited(policy_id, query)
    except Exception:
        pass


def _is_rate_limited_text(text: str) -> bool:
    try:
        from ingestion.core.error_taxonomy import is_rate_limited_text
        return is_rate_limited_text(text)
    except Exception:
        return False


def _registry_endpoint(provider_id: str) -> Optional[str]:
    """source_registry(_SERVICE_CONFIGS)에서 endpoint 만 읽는다(하드코딩 0·secret 0·key 값 안 읽음)."""
    try:
        from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS
        cfg = _SERVICE_CONFIGS.get(provider_id) or {}
        return cfg.get("endpoint")
    except Exception:
        return None


# ── time-window → date range(today 주입 시 결정론·테스트 안정) ────────────────────────────────────────────
def _window_dates(time_window: str, today: Optional[str]) -> tuple[str, str]:
    """time_window(1d/7d) → (from_date, to_date) YYYY-MM-DD. today 미주입 시 실 UTC 오늘(실 network 경로)."""
    days = 7 if str(time_window or "").strip().lower().startswith("7") else 1
    if today:
        end = datetime.strptime(today, "%Y-%m-%d").date()
    else:
        end = datetime.now(timezone.utc).date()
    return (end - timedelta(days=days)).isoformat(), end.isoformat()


def _in_window(published_at: Optional[str], from_date: str, to_date: str) -> bool:
    """record published date(YYYY-MM-DD)가 [from_date, to_date] 안인가(date-pin enforcement·strict).

    ADR#84 근거: Guardian/NYT 는 from-date/to-date 가 URL 에 정확히 들어가도(검증됨) 실 응답에서 그 window 를
    무시하고 최신(out-of-window) 기사를 반환할 수 있다(또는 in-window 보도 0). 그 경우 date-pin 은 실효 0이 된다.
    이 가드는 provider 신뢰가 아니라 adapter 가 window 를 강제한다 — 날짜 없음/형식 불명/범위 밖은 제외
    (strict precision: 같은 pinned window 의 cross-source 후보만 남긴다). ISO date 는 사전식 비교가 날짜 비교와 일치."""
    if not published_at or len(published_at) < 10:
        return False
    return from_date <= published_at[:10] <= to_date


def _iso_date(pub: Optional[str]) -> Optional[str]:
    """ISO8601 timestamp(webPublicationDate) → YYYY-MM-DD(date bucket 호환). 실패 시 원문 유지."""
    if not pub:
        return None
    p = pub.strip()
    if len(p) >= 10 and p[4] == "-" and p[7] == "-":
        return p[:10]
    return p


# ── Guardian: URL builder(secret 은 실 network 경로에서만) + parser(공식 shape·본문 미저장) ────────────────
def _guardian_url(
    endpoint: str, *, topic: str, from_date: str, to_date: str, max_records: int,
) -> str:
    """Guardian Content API /search URL(q·from-date·to-date·page-size·order-by). **api-key 는 URL 에 넣지 않는다**
    — secret hygiene(adversarial LOW-2 하드닝): url 문자열을 항상 keyless 로 유지해 향후 로깅 사고를 구조적으로 차단.
    실 network 경로는 key 를 httpx `params` 로만 전달한다(run_provider_query)."""
    return endpoint + "?" + urlencode({
        "q": topic, "from-date": from_date, "to-date": to_date,
        "page-size": str(max_records), "order-by": "newest",
    })


def parse_guardian_items(
    payload: str, *, max_records: int = _DEFAULT_MAX_RECORDS,
) -> Optional[list[dict]]:
    """Guardian Content API JSON → `_rec`(title≤512·canonical=webUrl·published=webPublicationDate·**본문 미저장**).

    공식 shape: {"response": {"status": "ok", "results": [{"webTitle","webUrl","webPublicationDate", ...}]}}.
    파싱 실패/status!=ok/results 부재 → None(parser_error). 같은 사건을 다른 기사·다른 URL 로 보도 →
    near_match_below_fingerprint(reviewer-zone)의 생성원. record_type=article_candidate → source role=article(publishable)."""
    try:
        data = json.loads(payload)
    except Exception:
        return None
    resp = data.get("response") if isinstance(data, dict) else None
    if not isinstance(resp, dict):
        return None
    if resp.get("status") and resp.get("status") != "ok":
        return None
    results = resp.get("results")
    if not isinstance(results, list):
        return None
    recs: list[dict] = []
    for art in results[:max_records]:
        if not isinstance(art, dict):
            continue
        title = (art.get("webTitle") or "").strip()
        url = (art.get("webUrl") or "").strip()
        if not title or not url:
            continue
        recs.append(_rec(
            record_type="article_candidate", source_id="guardian",
            title_or_label=title[:512], canonical_url=url, source_url_or_evidence=url,
            published_at_or_observed_at=_iso_date(art.get("webPublicationDate")),
            body_state_or_signal="present"))   # source 측 본문 존재 신호일 뿐 — 저장 안 함(_rec 에 body 필드 없음).
    return recs


def _nyt_url(
    endpoint: str, *, topic: str, from_date: str, to_date: str, max_records: int,
) -> str:
    """NYT Article Search /articlesearch.json URL(q·begin_date·end_date·sort=newest). **api-key 는 URL 에 넣지 않는다**
    — keyless(secret hygiene·Guardian 과 동일); 실 network 경로는 key 를 httpx `params` 로만 전달(run_provider_query).
    NYT date 형식은 YYYYMMDD(대시 제거). page-size 파라미터 없음(고정 10/page) — max_records 는 parser 가 cap."""
    return endpoint + "?" + urlencode({
        "q": topic, "begin_date": from_date.replace("-", ""), "end_date": to_date.replace("-", ""),
        "sort": "newest",
    })


def parse_nyt_items(
    payload: str, *, max_records: int = _DEFAULT_MAX_RECORDS,
) -> Optional[list[dict]]:
    """NYT Article Search JSON → `_rec`(title≤512=headline.main·canonical=web_url·published=pub_date·**본문 미저장**).

    공식 shape: {"status":"OK","response":{"docs":[{"headline":{"main"},"web_url","pub_date", ...}]}}.
    파싱 실패/status!=OK/docs 부재 → None(parser_error). 같은 사건을 Guardian 과 다른 매체·다른 URL 로 보도 →
    cross-source near_match_below_fingerprint(reviewer-zone)의 생성원. record_type=article_candidate → role=article(publishable)."""
    try:
        data = json.loads(payload)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("status") and data.get("status") != "OK":
        return None
    resp = data.get("response")
    if not isinstance(resp, dict):
        return None
    docs = resp.get("docs")
    if not isinstance(docs, list):
        return None
    recs: list[dict] = []
    for art in docs[:max_records]:
        if not isinstance(art, dict):
            continue
        hl = art.get("headline")
        # headline 은 보통 {"main": ...}; 일부 응답은 문자열. dict/str 외(list/숫자 등 malformed)는 빈 title 로
        # 강등해 skip(code-review MEDIUM: `.strip()` AttributeError 가 run_provider_query 까지 전파되는 것 방지).
        title = hl.get("main") if isinstance(hl, dict) else hl
        title = (title if isinstance(title, str) else "").strip()
        url = (art.get("web_url") or "").strip()
        if not title or not url:
            continue
        recs.append(_rec(
            record_type="article_candidate", source_id="nyt",
            title_or_label=title[:512], canonical_url=url, source_url_or_evidence=url,
            published_at_or_observed_at=_iso_date(art.get("pub_date")),
            body_state_or_signal="present"))
    return recs


_URL_BUILDERS: dict[str, Callable[..., str]] = {"guardian": _guardian_url, "nyt": _nyt_url}
_PARSERS: dict[str, Callable[..., Optional[list[dict]]]] = {
    "guardian": parse_guardian_items, "nyt": parse_nyt_items}


# ── 공통 governed live query(opt-in·network·CI 아님; transport 주입 시 결정론·network 0) ──────────────────
def run_provider_query(
    provider: str, *, topic: str, time_window: str = "1d",
    max_records: Optional[int] = None,
    transport: Optional[Callable[[str], Optional[str]]] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    host_gate: Any = None, today: Optional[str] = None,
    enforce_window: bool = False,
) -> ProviderQueryResult:
    """contract adapter 로 bounded governed live query. gate 순서(fail-closed): adapter 미배선→fetcher_not_wired;
    credential missing→missing_credentials(**network 전**); rate-limit cooldown→rate_limited; host gate→
    host_gate_blocked; 그 다음에만 fetch. 실패는 §5 status 로 분류. secret 값 0·raw body 미저장·no DB/merge/LLM.

    transport(url)→payload 주입 시 결정론(test·network 0·key 불요). 미주입 시 실 network(opt-in·key os.getenv·로그 0)."""
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        return ProviderQueryResult(
            provider, ST_FETCHER_NOT_WIRED, block_reason="fetcher_not_wired",
            next_action=f"no contract adapter for {provider} (gdelt/rss=ADR#60 native·그 외 미배선)")
    env_fn = env_status_fn or _default_env_status
    # max_records is None 일 때만 adapter 기본값(0 은 명시적 0 으로 존중 — falsy-zero 치환 금지·code-review).
    maxr = adapter.max_records if max_records is None else max_records

    # 1) credential(secret-safe·network 전) — 미충족이면 즉시 missing_credentials.
    if adapter.auth_required:
        present = env_fn(list(adapter.required_env_vars))
        missing = [k for k in adapter.required_env_vars if present.get(k) != "present"]
        if missing:
            return ProviderQueryResult(
                provider, ST_MISSING_CREDENTIALS, block_reason="missing_credentials",
                next_action=f"set_env:{','.join(missing)} (.env 에 값 설정·secret 커밋 금지) 후 --live-query")

    # 2) rate-limit cooldown(no tight retry) — 진행 중이면 fetch 안 함.
    cooling, retry_at = _in_cooldown(adapter.rate_limit_policy_id, topic)
    if cooling:
        return ProviderQueryResult(
            provider, ST_RATE_LIMITED, block_reason="provider_429_cooldown",
            next_action=f"respect_cooldown:{provider} until {retry_at} (no tight retry)")

    # 3) host gate(shared·no-bypass) — gate 주입 시에만 참여(미주입=단발 best-effort).
    if host_gate is not None and adapter.host_gate_key:
        try:
            dec = host_gate.decide(
                adapter.host_gate_key, min_spacing_seconds=adapter.host_min_spacing_seconds)
            if not getattr(dec, "allowed", True):
                return ProviderQueryResult(
                    provider, ST_HOST_GATE_BLOCKED,
                    block_reason=getattr(dec, "reason", None) or "host_min_spacing_not_elapsed",
                    next_action=f"respect_host_gate:{adapter.host} (shared floor·no-bypass)")
            host_gate.record_call(adapter.host_gate_key)   # 실 HTTP 직전 기록.
        except Exception:
            pass

    # 4) endpoint(registry·하드코딩 0).
    endpoint = _registry_endpoint(provider)
    if not endpoint:
        return ProviderQueryResult(
            provider, ST_FETCHER_NOT_WIRED, block_reason="no_endpoint",
            next_action=f"registry endpoint missing for {provider}")
    from_date, to_date = _window_dates(time_window, today)
    url_builder = _URL_BUILDERS[provider]
    parser = _PARSERS[provider]

    # 5) fetch — transport(test·key 불요) OR 실 network(opt-in·key os.getenv·params 전용·로그 0).
    url = url_builder(endpoint, topic=topic, from_date=from_date, to_date=to_date, max_records=maxr)
    if transport is not None:
        payload = transport(url)   # url 은 keyless — fake transport 가 받아도 secret 0.
        if payload is None:
            return ProviderQueryResult(
                provider, ST_NETWORK_ERROR, block_reason="network_error", next_action="retry later")
    else:
        import os
        # api-key 는 keyless url 에 concat 하지 않고 httpx params 로만 전달(secret hygiene·로그 사고 방지·LOW-2).
        api_key = os.getenv(adapter.required_env_vars[0]) if adapter.auth_required else None
        try:
            import httpx
            r = httpx.get(url, params=({"api-key": api_key} if api_key else None),
                          timeout=20.0, follow_redirects=True, headers={"User-Agent": _BROWSER_UA})
        except Exception:
            return ProviderQueryResult(
                provider, ST_NETWORK_ERROR, block_reason="network_error", next_action="retry later")
        text = r.text or ""
        if r.status_code == 429 or _is_rate_limited_text(text):
            _record_rate_limited(adapter.rate_limit_policy_id, topic)   # cooldown 영속(no tight retry).
            return ProviderQueryResult(
                provider, ST_RATE_LIMITED, block_reason="rate_limited",
                next_action=f"respect_cooldown:{provider} (no tight retry)")
        if "json" not in (r.headers.get("content-type") or "").lower():
            return ProviderQueryResult(
                provider, ST_PARSER_ERROR, block_reason="parser_error",
                next_action="provider returned non-JSON")
        payload = text

    # 6) parse → `_rec` records(본문 미저장). None=parser_error·빈 목록=no_records.
    recs = parser(payload, max_records=maxr)
    if recs is None:
        return ProviderQueryResult(
            provider, ST_PARSER_ERROR, block_reason="parser_error",
            next_action="unexpected payload shape")
    # 6b) date-pin window enforcement(opt-in·additive·ADR#84): provider 가 from-date/to-date 를 무시하고
    # out-of-window 기사를 반환해도 [from_date, to_date] 밖 record 를 drop(date-pin 계약을 adapter 가 강제).
    # 기본 False=ADR#62~#82 동작 보존(필터 0). True 면 provider 가 200개를 줘도 window 밖은 같은 사건 후보가
    # 아니므로 제외 — out-of-window 만 남아 전부 drop 되면 no_in_window_records 로 정직 분리(진짜 0 records 와 구분).
    pre_filter_count = len(recs)
    if enforce_window:
        recs = [r for r in recs if _in_window(r.get("published_at_or_observed_at"), from_date, to_date)]
    if not recs:
        if enforce_window and pre_filter_count > 0:
            return ProviderQueryResult(
                provider, ST_NO_RECORDS, block_reason="no_in_window_records",
                next_action=(f"provider returned {pre_filter_count} record(s) but none within the pinned "
                             f"[{from_date},{to_date}] window — provider ignored the date filter or there is "
                             f"no in-window cross-source coverage; verify occurrence_date or widen the window"))
        return ProviderQueryResult(
            provider, ST_NO_RECORDS, block_reason="no_records",
            next_action="broaden topic/time_window")
    return ProviderQueryResult(provider, ST_OK, records=recs, records_count=len(recs),
                               provenance="live_derived")


# ── readiness/agent schema 가 adapter wiring 상태를 반영할 contract 메타데이터(secret 0) ────────────────────
def adapter_descriptor(provider: str) -> Optional[dict]:
    """wired contract adapter 의 메타데이터(없으면 None). fetch_implemented=True 는 실 parser+fake-transport test
    통과를 전제(test_provider_query_adapters 가 잠금) — stub/skeleton 은 여기 등재 금지."""
    a = _ADAPTERS.get(provider)
    if a is None:
        return None
    return {
        "adapter_contract_version": ADAPTER_CONTRACT_VERSION,
        "adapter_module": f"backend.app.tools.provider_query_adapters:{provider}",
        "fetch_implemented": a.fetch_implemented,
        "supports_topic_query": a.supports_topic_query,
        "supports_time_window": a.supports_time_window,
        "supports_source_pair": a.supports_source_pair,
        "max_records": a.max_records,
        "rate_limit_policy_id": a.rate_limit_policy_id,
        "host_gate_key": a.host_gate_key,
        "host_min_spacing_seconds": a.host_min_spacing_seconds,
        "tested_with_fake_transport": True,
        "parser_contract_status": "implemented",
        "record_normalization_status": "rec_title_canonical_published_no_body",
        "queue_integration_status": "wired",   # adapter records → ADR#60 records= → discover → near-match queue.
    }


def provider_adapter_contract() -> dict:
    """옵션 A — provider fetcher 가 따라야 할 공통 contract 표면(§5). 문서/테스트/Agent 가 같은 계약을 본다."""
    return {
        "contract_version": ADAPTER_CONTRACT_VERSION,
        "adapter_fields": [
            "provider_id", "query_capable", "auth_required", "required_env_vars", "fetch_implemented",
            "supports_topic_query", "supports_time_window", "supports_source_pair", "max_records",
            "rate_limit_policy_id", "host", "host_gate_key", "host_min_spacing_seconds"],
        "result_fields": [
            "provider_id", "status", "records", "records_count", "raw_body_stored", "secret_exposed",
            "provenance", "block_reason", "next_action"],
        "record_fields": [
            "record_type", "source_id", "title_or_label", "canonical_url",
            "source_url_or_evidence", "published_at_or_observed_at", "body_state_or_signal"],
        "status_vocabulary": [
            ST_OK, ST_MISSING_CREDENTIALS, ST_RATE_LIMITED, ST_HOST_GATE_BLOCKED,
            ST_FETCHER_NOT_WIRED, ST_NETWORK_ERROR, ST_PARSER_ERROR, ST_NO_RECORDS,
            ST_DISABLED, ST_UNKNOWN],
        "forbidden": [
            "raw_body_storage", "secret_value_exposure", "db_write", "merge",
            "public_intelligence_unit", "llm_call"],
        "wired_providers": sorted(ADAPTER_WIRED_PROVIDERS),
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "llm_invoked": False,
    }
