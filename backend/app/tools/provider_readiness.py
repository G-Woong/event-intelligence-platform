"""ADR#61 — query-capable provider acquisition readiness gate.

ADR#60 이 정직하게 남긴 한계: targeted same-event acquisition 의 detection-layer 운영 경로(discover→queue→
reviewer/gold)는 닫혔으나 **실 near-match 후보는 0** — 그 직접 원인은 queue 실패가 아니라 *query-capable provider
acquisition failure* 였다(분석 §2-Q20). 이 모듈은 그 blocker 를 정직하게 닫는다. 자동 병합 턴도, LLM 본경로 턴도,
운영 DB 배포 턴도 아니다 — **실 near-match 후보를 만들 provider gate 를 닫고, 후보가 없으면 No-Go 를 정직하게
산출하는 acquisition readiness 턴**이다.

무엇을 하는가:
  - 어떤 query-capable provider 가 key-free / key-required / blocked(rate-limited) / disabled / unknown 인지
    readiness report 로 분류한다(§5).
  - credential(env present)·host gate·rate-limit cooldown 을 **동시에** 본다(단순 env 존재 체크로 축소 금지).
  - provider key/cooldown 이 막으면 clear No-Go + next_action 을 산출한다(fixture 위장 금지).
  - opt-in bounded live query 가 **안전·허용**될 때만 실 fetch 를 시도하고, 산출된 후보를 near-match reviewer
    queue 로 연결한다(§6/§7). 후보가 없으면 empty queue + block_reason + next_action 으로 정직히 노출한다.

재구현 0 — 무거운 일은 전부 기존 단일 출처가 한다:
  - credential presence(secret-safe): `ingestion.core.env_loader.env_status`(present/missing·**값 미노출**·alias 해소)
  - host gate / 429 cooldown 합성: `source_overlap_discovery.gdelt_provider_status`(HostRateGate+in_cooldown·read-only)
  - rate-limit policy: `ingestion.core.rate_limit_policy.load_rate_limit_policy`
  - 실 fetch→discover→queue: `targeted_same_event_acquisition.run_targeted_same_event_operating_readiness`(ADR#60)

절대 불변(상속·재확인 — 상용 안전 계약):
  - **no merge / no auto-merge**·LLM/embedding 호출 0·운영 DB 미접촉(옵션 E/F 금지)·production_gold 0.
  - **synthetic↔live 봉인**: real_fetch 단일 boolean 이 dataset_source 를 결정(provider 가 막히면 fixture 로
    둔갑 금지·dataset_source=None). 실 후보가 없으면 no_candidate/block_reason 으로 드러낸다.
  - **source role guard**(publishable×publishable 만)·community reaction/market/catalog 는 event anchor 금지.
  - provider **secret 값은 출력·로그 0**(env var 이름·present/missing boolean 만).
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Callable, Optional

from backend.app.tools.near_match_reviewer_queue import EMBEDDING_LLM_ADJUDICATOR_INTERFACE
from backend.app.tools.source_overlap_discovery import gdelt_provider_status
from backend.app.tools.targeted_same_event_acquisition import (
    _DEFAULT_TARGET_SOURCES,
    run_targeted_same_event_operating_readiness,
)

# ADR#60 fetch layer(run_targeted_acquisition)가 인식하는 provider 토큰. readiness catalog 의 표시명("rss_fleet")과
# 다르므로 live query 호출 직전 정규화한다(미정규화 시 'rss_fleet' 이 fixture 로 silent 낙하 — code-review/adversarial MEDIUM).
_ACQ_PROVIDER_ALIAS = {"rss_fleet": "rss"}

# ── provider classification buckets(§5) ───────────────────────────────────────────────────────────────
CLASS_KEY_FREE_QUERY = "key_free_query_capable"
CLASS_KEY_REQUIRED_QUERY = "key_required_query_capable"
CLASS_KEY_FREE_NON_QUERY = "key_free_non_query"
CLASS_BLOCKED_RATE_LIMITED = "blocked_rate_limited"
CLASS_DISABLED = "disabled"
CLASS_UNKNOWN_POLICY = "unknown_policy"

# ── optional live query 실패/skip 분류(§6) ────────────────────────────────────────────────────────────
LQ_NOT_OPTED_IN = "live_query_not_opted_in"
LQ_MISSING_CREDENTIALS = "missing_credentials"
LQ_PROVIDER_RATE_LIMITED = "provider_rate_limited"
LQ_HOST_GATE_BLOCKED = "host_gate_blocked"
LQ_NETWORK_ERROR = "network_error"
LQ_PARSER_ERROR = "parser_error"
LQ_NO_RECORDS = "no_records"
LQ_NO_NEAR_MATCH = "no_near_match"
LQ_NO_QUERY_CAPABLE_PROVIDER = "no_query_capable_provider"
# query-capable·credential-ready 이나 이번 acquisition 경로(run_targeted_acquisition)에 실 fetcher 미배선
# (gdelt/rss 만 배선). fixture 로 조용히 떨어지지 않게 정직히 차단(분석 §2-Q20·honest limit).
LQ_FETCHER_NOT_IMPLEMENTED = "fetcher_not_wired"

# fetch-stage block_reason(run_targeted_acquisition/source_overlap_discovery 산출) → §6 분류 정규화.
_FETCH_REASON_MAP = {
    "rate_limited": LQ_PROVIDER_RATE_LIMITED,
    "provider_429_cooldown": LQ_PROVIDER_RATE_LIMITED,
    "host_rate_limited": LQ_HOST_GATE_BLOCKED,
    "host_min_spacing_not_elapsed": LQ_HOST_GATE_BLOCKED,
    "network_error": LQ_NETWORK_ERROR,
    "parser_error": LQ_PARSER_ERROR,
    "no_records": LQ_NO_RECORDS,
    "rss_no_records": LQ_NO_RECORDS,
}

# ── curated query-capability catalog ───────────────────────────────────────────────────────────────────
# 코드베이스는 "query-capable" 단일 flag 가 없고(파이프라인 query 레이어는 stub) registry 는 auth/env_keys 만 가진다
# (분석 §2-Q1·Q9). 이 catalog 는 **same-event cross-source near-match 에 쓸 수 있는 news/official 텍스트 provider**의
# query 능력·host·auth·env var(실 os.getenv 이름)·robots/tos·raw-body 정책을 명시한다. credential/cooldown 같은
# **동적** readiness 는 catalog 가 아니라 env_status/host_gate/rate_limit_policy 에서 실측한다(하드코딩 readiness 금지).
# 주의: query_capability 는 외부 API 계약에 대한 **큐레이트 선언**(코드로 미검증)이며 fetcher 배선 시 첫 실 호출로
# 검증돼야 한다 — fetch_implemented=False 인 동안은 런타임 영향 0(미배선 provider 는 live query 자체가 차단).
# required_env_vars/auth 는 source_registry.yaml env_keys 와 중복 — rename 시 동기화 필요(test 가 .env.example 존재만 보장).
# 의도적으로 제외: market(finnhub/polygon/binance…)·domain/catalog(tmdb/kopis…)·community(youtube/reddit…)·
# official data(opendart/bok_ecos/eia=filings/stats) — 이들은 enrichment 이지 same-event news anchor 가 아니다(§18).
_RAW_BODY_POLICY = "title+canonical_only_no_body"

_PROVIDER_CATALOG: dict[str, dict] = {
    # ── key-free, topic-query-capable(키 없이 targeted query 가능한 유일군) ──
    "gdelt": {
        "source_ids": ["gdelt"], "query_capability": "topic+time_window",
        "auth_required": False, "required_env_vars": [],
        "host": "api.gdeltproject.org", "host_gated": True,
        "robots_tos_status": "public_api_documented_soft_rate_limit",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "news_aggregator",
    },
    "sec_edgar": {
        "source_ids": ["sec_edgar"], "query_capability": "full_text_search",
        "auth_required": False, "required_env_vars": [],   # SEC_USER_AGENT 은 UA 만(credential gate 아님).
        "host": "efts.sec.gov", "host_gated": False,
        "robots_tos_status": "public_api_fair_access_ua_requested",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "official_filings",
    },
    "federal_register": {
        "source_ids": ["federal_register"], "query_capability": "topic+time_window",
        "auth_required": False, "required_env_vars": [],
        "host": "www.federalregister.gov", "host_gated": False,
        "robots_tos_status": "public_api_documented",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "official_register",
    },
    # ── key-required, topic-query-capable news/search(.env.example placeholder 이미 존재) ──
    "newsapi": {
        "source_ids": ["newsapi"], "query_capability": "topic+time_window",
        "auth_required": True, "required_env_vars": ["NEWSAPI_API_KEY"],
        "host": "newsapi.org", "host_gated": False,
        "robots_tos_status": "requires_key_per_tos",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "news_search",
    },
    "gnews": {
        "source_ids": ["gnews"], "query_capability": "topic+time_window",
        "auth_required": True, "required_env_vars": ["GNEWS_API_KEY"],
        "host": "gnews.io", "host_gated": False,
        "robots_tos_status": "requires_key_per_tos",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "news_search",
    },
    "guardian": {
        "source_ids": ["guardian"], "query_capability": "topic+time_window",
        "auth_required": True, "required_env_vars": ["GUARDIAN_API_KEY"],
        "host": "content.guardianapis.com", "host_gated": False,
        "robots_tos_status": "requires_key_per_tos",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "news",
    },
    "nyt": {
        "source_ids": ["nyt"], "query_capability": "topic+time_window",
        "auth_required": True, "required_env_vars": ["NYT_API_KEY"],
        "host": "api.nytimes.com", "host_gated": False,
        "robots_tos_status": "requires_key_per_tos",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "news",
    },
    "naver_news_search": {
        "source_ids": ["naver_news_search"], "query_capability": "topic",
        "auth_required": True, "required_env_vars": ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"],
        "host": "openapi.naver.com", "host_gated": False,
        "robots_tos_status": "requires_key_per_tos",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "news_search",
    },
    "serper": {
        "source_ids": ["serper"], "query_capability": "topic",
        "auth_required": True, "required_env_vars": ["SERPER_API_KEY"],
        "host": "google.serper.dev", "host_gated": False,
        "robots_tos_status": "requires_key_per_tos",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "web_search",
    },
    "tavily": {
        "source_ids": ["tavily"], "query_capability": "topic",
        "auth_required": True, "required_env_vars": ["TAVILY_API_KEY"],
        "host": "api.tavily.com", "host_gated": False,
        "robots_tos_status": "requires_key_per_tos",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "web_search",
    },
    "exa": {
        "source_ids": ["exa"], "query_capability": "topic",
        "auth_required": True, "required_env_vars": ["EXA_API_KEY"],
        "host": "api.exa.ai", "host_gated": False,
        "robots_tos_status": "requires_key_per_tos",
        "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "web_search",
    },
}

# key-free FEED-ONLY 함대(topic query **불가** — time-window+source-pair targeting 만). source_ids 는 실 fetch 가
# 쓰는 ADR#60 `_DEFAULT_TARGET_SOURCES` 를 단일 출처로 재사용(별도 하드코딩 시 발산 — code-review SIMPLIFICATION).
_NON_QUERY_KEY_FREE_FLEET: dict = {
    "provider_id": "rss_fleet",
    "source_ids": list(_DEFAULT_TARGET_SOURCES),
    "query_capability": "time_window+source_pair",
    "auth_required": False, "required_env_vars": [],
    "host": None, "host_gated": False,
    "robots_tos_status": "rss_or_public_feed",
    "raw_body_policy": _RAW_BODY_POLICY, "enabled": True, "category": "rss_feed",
}

# 이번 acquisition 경로(targeted_same_event_acquisition.run_targeted_acquisition)에 **실 fetcher 가 배선된** provider.
# 코드 사실(catalog 데이터 아님): gdelt(fetch_gdelt_overlap_records)·rss_fleet(fetch_rss_overlap_records)만 존재.
# 나머지(sec_edgar/federal_register/newsapi/…)는 query-capable 이나 미배선 → live query 시 fixture 로 떨어지지 않게
# fetcher_not_wired 로 정직 차단(확장 후보).
_FETCH_WIRED_PROVIDERS = frozenset({"gdelt", "rss_fleet"})


def _default_env_status(keys: list[str]) -> dict[str, str]:
    """secret-safe credential presence — ingestion.core.env_loader.env_status 재사용(값 미노출·alias 해소).

    실패(import/parse)해도 죽지 않고 전부 missing 으로 보수 처리(fail-closed)."""
    if not keys:
        return {}
    try:
        from ingestion.core.env_loader import env_status
        return env_status(list(keys))
    except Exception:
        return {k: "missing" for k in keys}


def _rate_limit_policy(provider_id: str) -> dict:
    """effective rate-limit policy(default+per_source merge). load 실패해도 죽지 않게 보수 기본값."""
    try:
        from ingestion.core.rate_limit_policy import load_rate_limit_policy
        pol = load_rate_limit_policy(provider_id)
        return {
            "min_interval_seconds": pol.min_interval_seconds,
            "cooldown_on_429_seconds": pol.cooldown_on_429_seconds,
            "max_retries_on_429": pol.max_retries_on_429,
        }
    except Exception:
        return {"min_interval_seconds": 0, "cooldown_on_429_seconds": 60, "max_retries_on_429": 1}


def _next_action(
    *, classification: str, provider_id: str, credential_ready: bool,
    required: list[str], env_present: dict[str, str], safe: bool, block: Optional[str],
    fetch_implemented: bool,
) -> str:
    """provider 별 정확한 다음 행동(secret 값 0·env var 이름만)."""
    if classification == CLASS_DISABLED:
        return f"provider_disabled:{provider_id} (registry 비활성 — 이번 턴 범위 밖)"
    if classification == CLASS_UNKNOWN_POLICY:
        return f"unknown_provider:{provider_id} — registry/policy review 필요(fail-closed·추측 금지)"
    if classification == CLASS_KEY_FREE_NON_QUERY:
        return "time_window+source_pair targeting only — topic query 불가(RSS feed-only)"
    if classification == CLASS_BLOCKED_RATE_LIMITED:
        return (f"respect_cooldown:{provider_id} ({block or 'rate_limited'}) — "
                "no tight retry·cooldown 만료 후 재시도")
    if not credential_ready:
        missing = [k for k in required if env_present.get(k) != "present"]
        return (f"set_env:{','.join(missing)} (.env 에 값 설정 — secret 커밋 금지) 후 --live-query 활성")
    if not fetch_implemented:
        return (f"wire_fetcher:{provider_id} — query-capable·credential-ready 이나 이번 acquisition 경로는 "
                "gdelt/rss 만 실 fetch 배선(확장 후보)")
    if safe:
        return f"live_query_ready:{provider_id} (--live-query opt-in 시 bounded governed fetch 가능)"
    return f"hold:{provider_id} (safe_to_live_query=False)"


def _classify_provider(
    provider_id: str, spec: dict, *,
    env_status_fn: Callable[[list[str]], dict[str, str]],
    gdelt_status: dict,
) -> dict:
    """단일 provider readiness row(§5 필수 필드). credential/cooldown 은 실측·하드코딩 금지."""
    auth_required = bool(spec.get("auth_required"))
    required = list(spec.get("required_env_vars") or [])
    # credential presence(secret-safe — present/missing boolean 만·값 미노출).
    env_present = env_status_fn(required) if required else {}
    credential_ready = (not auth_required) or all(
        env_present.get(k) == "present" for k in required)
    host_gated = bool(spec.get("host_gated"))
    fetch_implemented = provider_id in _FETCH_WIRED_PROVIDERS
    rate_limit_policy = _rate_limit_policy(provider_id)

    host_gate_status = "not_host_gated"
    current_cooldown: Optional[str] = None
    # safe_to_live_query = credential 준비 + (host gate clear) + **실 fetcher 배선**(미배선이면 실 query 불가).
    safe = credential_ready and fetch_implemented
    block: Optional[str] = None
    if host_gated and provider_id == "gdelt":
        # gdelt_provider_status 가 HostRateGate(host floor)+in_cooldown(429)을 read-only 합성(network 0).
        host_gate_status = gdelt_status.get("provider_status", "unknown")
        if host_gate_status != "ok":
            safe = False
            block = gdelt_status.get("provider_block_reason")
            current_cooldown = gdelt_status.get("retry_after_or_cooldown") or block

    # classification bucket(disabled > non-query > blocked > key-required > key-free 순).
    if not spec.get("enabled", True):
        classification = CLASS_DISABLED
    elif spec.get("query_capability") == "time_window+source_pair":
        classification = CLASS_KEY_FREE_NON_QUERY
    elif host_gated and provider_id == "gdelt" and host_gate_status != "ok":
        classification = CLASS_BLOCKED_RATE_LIMITED
    elif auth_required:
        classification = CLASS_KEY_REQUIRED_QUERY
    else:
        classification = CLASS_KEY_FREE_QUERY

    next_action = _next_action(
        classification=classification, provider_id=provider_id, credential_ready=credential_ready,
        required=required, env_present=env_present, safe=safe, block=block,
        fetch_implemented=fetch_implemented)
    return {
        "provider_id": provider_id,
        "source_ids": list(spec.get("source_ids") or []),
        "query_capability": spec.get("query_capability"),
        "auth_required": auth_required,
        "required_env_vars": required,
        "env_present": env_present,                 # {VAR: present|missing} — 이름+boolean 만(값 0).
        "credential_ready": credential_ready,
        "fetch_implemented": fetch_implemented,
        "rate_limit_policy_present": True,
        "rate_limit_policy": rate_limit_policy,
        "host_gate_supported": host_gated,
        "host_gate_status": host_gate_status,
        "current_cooldown": current_cooldown,
        "robots_tos_status": spec.get("robots_tos_status"),
        "raw_body_policy": spec.get("raw_body_policy"),
        "safe_to_live_query": bool(safe),
        "classification": classification,
        "next_action": next_action,
        "no_merge_without_gate": True,
    }


def _unknown_provider_row(provider_id: str) -> dict:
    """catalog 에 없는 provider 요청 → fail-closed unknown(safe_to_live_query=False)."""
    return {
        "provider_id": provider_id, "source_ids": [], "query_capability": None,
        "auth_required": None, "required_env_vars": [], "env_present": {},
        "credential_ready": False, "fetch_implemented": False, "rate_limit_policy_present": False,
        "rate_limit_policy": {}, "host_gate_supported": False,
        "host_gate_status": "unknown", "current_cooldown": None,
        "robots_tos_status": "unknown_requires_legal_review", "raw_body_policy": _RAW_BODY_POLICY,
        "safe_to_live_query": False, "classification": CLASS_UNKNOWN_POLICY,
        "next_action": _next_action(
            classification=CLASS_UNKNOWN_POLICY, provider_id=provider_id, credential_ready=False,
            required=[], env_present={}, safe=False, block=None, fetch_implemented=False),
        "no_merge_without_gate": True,
    }


# ── §5: provider readiness report(옵션 A — pure·network 0·아래 buckets 집계) ─────────────────────────────
def build_provider_readiness_report(
    *, providers: Optional[list[str]] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    host_gate: Any = None, gdelt_status: Optional[dict] = None,
    include_non_query_fleet: bool = True,
) -> dict:
    """query-capable provider readiness 를 key-free/key-required/blocked/disabled/unknown 으로 분류(§5).

    credential(env present)·host gate·rate-limit cooldown 을 동시에 본다. **network 0**(gdelt 는 host gate 상태만
    read-only 조회). secret 값 0 — env var 이름·present/missing boolean 만. test 는 env_status_fn/gdelt_status
    주입으로 실 .env/state 비의존 결정론."""
    env_fn = env_status_fn or _default_env_status
    if gdelt_status is None:
        try:
            gdelt_status = gdelt_provider_status(host_gate=host_gate)
        except Exception:
            gdelt_status = {"provider_status": "unknown",
                            "provider_block_reason": "gdelt_status_unavailable"}

    if providers is None:
        requested = list(_PROVIDER_CATALOG.keys())
        if include_non_query_fleet:
            requested.append("rss_fleet")
    else:
        requested = list(providers)

    rows: list[dict] = []
    for pid in requested:
        if pid == "rss_fleet":
            rows.append(_classify_provider(
                "rss_fleet", _NON_QUERY_KEY_FREE_FLEET, env_status_fn=env_fn,
                gdelt_status=gdelt_status))
        elif pid in _PROVIDER_CATALOG:
            rows.append(_classify_provider(
                pid, _PROVIDER_CATALOG[pid], env_status_fn=env_fn, gdelt_status=gdelt_status))
        else:
            rows.append(_unknown_provider_row(pid))

    query_capable = [
        r["provider_id"] for r in rows
        if r["classification"] in (CLASS_KEY_FREE_QUERY, CLASS_KEY_REQUIRED_QUERY,
                                   CLASS_BLOCKED_RATE_LIMITED)]
    key_free_ready = [
        r["provider_id"] for r in rows
        if r["classification"] == CLASS_KEY_FREE_QUERY and r["safe_to_live_query"]]
    key_required_missing = [
        r["provider_id"] for r in rows
        if r["classification"] == CLASS_KEY_REQUIRED_QUERY and not r["credential_ready"]]
    provider_blocked = [
        r["provider_id"] for r in rows if r["classification"] == CLASS_BLOCKED_RATE_LIMITED]
    provider_unknown = [
        r["provider_id"] for r in rows if r["classification"] == CLASS_UNKNOWN_POLICY]
    key_required_ready = [
        r["provider_id"] for r in rows
        if r["classification"] == CLASS_KEY_REQUIRED_QUERY and r["credential_ready"]]
    return {
        "providers": rows,
        "query_capable_providers": query_capable,
        "key_free_ready": key_free_ready,
        "key_required_ready": key_required_ready,
        "key_required_missing": key_required_missing,
        "provider_blocked": provider_blocked,
        "provider_unknown": provider_unknown,
        "env_var_requirements": {
            r["provider_id"]: r["required_env_vars"] for r in rows if r["required_env_vars"]},
        "credential_status": {r["provider_id"]: r["credential_ready"] for r in rows},
        "host_gate_status": {
            r["provider_id"]: r["host_gate_status"] for r in rows if r["host_gate_supported"]},
        "rate_limit_policy": {r["provider_id"]: r["rate_limit_policy"] for r in rows},
        "next_actions": {r["provider_id"]: r["next_action"] for r in rows},
        # 실 live query 가 지금 가능한 provider 가 하나라도 있는가(key-free ready OR key-required+credential).
        "any_live_query_ready": bool(key_free_ready or key_required_ready),
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "llm_invoked": False,
    }


# ── §6: optional bounded live query(provider 가 안전·허용될 때만 실 fetch·후보→queue) ──────────────────────
def run_optional_live_query(
    *, provider: str = "gdelt", topic: str = "central bank rate decision",
    topic_key: str = "central_bank_rate", time_window: str = "1d",
    source_ids: Optional[list[str]] = None, live_query: bool = False,
    readiness: Optional[dict] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    rss_transport: Optional[Callable[[str, str], Optional[str]]] = None,
    gdelt_transport: Optional[Callable[[str], Optional[str]]] = None,
    host_gate: Any = None, reviewers: Optional[list[str]] = None,
    packet_id: str = "live_near_match_pkt",
) -> dict:
    """opt-in bounded live query — readiness gate 통과(explicit flag + safe_to_live_query + credentials) 시에만
    실 governed fetch 를 시도하고, 산출 후보를 ADR#60 운영 경로(fetch→discover→near-match queue)로 연결한다.

    기본 live_query=False → 시도 0(skipped_reason=not_opted_in). 후보 0이면 no fixture substitution — empty queue +
    block_reason 으로 정직히 노출(dataset_source=None). 병합·LLM·DB write 0. test 는 transport 주입으로 network 0."""
    readiness = readiness if readiness is not None else build_provider_readiness_report(
        env_status_fn=env_status_fn, host_gate=host_gate)
    prow = next((r for r in readiness["providers"] if r["provider_id"] == provider), None)

    # ── gate: 무엇이 live query 를 막는가(fail-closed) ──
    skipped_reason: Optional[str] = None
    if not live_query:
        skipped_reason = LQ_NOT_OPTED_IN
    elif prow is None or prow["classification"] == CLASS_UNKNOWN_POLICY:
        skipped_reason = LQ_NO_QUERY_CAPABLE_PROVIDER
    elif prow["classification"] == CLASS_DISABLED:
        skipped_reason = LQ_NO_QUERY_CAPABLE_PROVIDER
    elif not prow["credential_ready"]:
        skipped_reason = LQ_MISSING_CREDENTIALS
    elif prow["classification"] == CLASS_BLOCKED_RATE_LIMITED:
        # host_gate_status 는 gdelt_provider_status 의 정확 enum(ok/cooldown/host_rate_limited) — substring 아닌 동치 비교.
        skipped_reason = (LQ_PROVIDER_RATE_LIMITED
                          if prow.get("host_gate_status") == "cooldown"
                          else LQ_HOST_GATE_BLOCKED)
    elif not prow.get("fetch_implemented"):
        # query-capable·credential-ready 이나 실 fetcher 미배선 → fixture 로 떨어지지 않게 정직 차단.
        skipped_reason = LQ_FETCHER_NOT_IMPLEMENTED
    elif not prow["safe_to_live_query"]:
        skipped_reason = LQ_HOST_GATE_BLOCKED

    live_query_allowed = skipped_reason is None
    block_reasons: list[str] = []
    result: Optional[dict] = None
    candidate_count = near = hard = fp = queue_population = 0
    dataset_source: Optional[str] = None
    provider_status_str: Optional[str] = prow.get("host_gate_status") if prow else None

    if not live_query_allowed:
        block_reasons.append(skipped_reason)
    else:
        # ADR#60 단일 진입 재사용 — live_network=True + transport(테스트 시 주입=network 0). fixture 둔갑 없음:
        # 실 fetch 가 0 후보면 ADR#60 이 block_reason 으로 노출하고 real_fetch 를 유지한다. provider 토큰은 ADR#60
        # 이 인식하는 형태로 정규화(rss_fleet→rss) — 미정규화 시 else 분기에서 synthetic fixture 로 silent 낙하.
        acq_provider = _ACQ_PROVIDER_ALIAS.get(provider, provider)
        out = run_targeted_same_event_operating_readiness(
            topic=topic, topic_key=topic_key, time_window=time_window, provider=acq_provider,
            source_ids=source_ids, live_network=True, rss_transport=rss_transport,
            gdelt_transport=gdelt_transport, host_gate=host_gate, reviewers=reviewers,
            packet_id=packet_id)
        rep = out["report"]
        candidate_count = rep["candidate_count"]
        near = rep["near_positive_count"]
        hard = rep["hard_negative_count"]
        fp = rep["fingerprint_overlap_count"]
        dataset_source = rep["dataset_source"]
        queue_population = len(out["queue"].get("queue_pair_ids") or [])
        if rep.get("block_reason"):
            block_reasons.append(_FETCH_REASON_MAP.get(rep["block_reason"], rep["block_reason"]))
        elif candidate_count == 0:
            block_reasons.append(LQ_NO_NEAR_MATCH)
        result = {
            "attempted": True,
            "provider_status": ("live_derived" if rep.get("real_fetch") else provider_status_str),
            "records_count": out["acquisition"].get("acquired_record_count", 0),
            "near_match_count": near,
            "hard_negative_count": hard,
            "fingerprint_overlap_count": fp,
            "reviewer_queue_population_count": queue_population,
            "packet_exportable": rep["reviewer_packet_exportable"],
            "production_gold_count": 0,
            "merge_allowed": False,
        }
    return {
        "provider": provider,
        "live_query_allowed": live_query_allowed,
        "live_query_attempted": bool(result),
        "skipped_reason": skipped_reason,
        "live_query_result": result,
        "candidate_count": candidate_count,
        "near_match_count": near,
        "hard_negative_count": hard,
        "fingerprint_overlap_count": fp,
        "reviewer_queue_population_count": queue_population,
        "dataset_source": dataset_source,
        "provenance": dataset_source or "none",   # 후보 없으면 fixture 둔갑 금지 — provenance 없음.
        "block_reasons": block_reasons,
        "production_gold_count": 0,
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "llm_invoked": False,
    }


# ── §9: Agent orchestration schema(provider readiness 포함·secret 추측 금지·merge 불가·LLM No-Go) ─────────
def build_provider_readiness_agent_schema(readiness: dict, live: dict) -> dict:
    """Agent 가 provider readiness·source-pair·reviewer queue population 을 **계획**할 수 있게 보강.

    Agent 불가: provider secret 추측/생성·같은 사건 확정·merge·public IU·community/market/catalog anchor.
    LLM 호출 0·embedding/LLM adjudicator 는 No-Go 유지."""
    return {
        "agent_can_plan": [
            "provider_readiness_review", "recommended_provider_setup", "source_pair_plan",
            "topic_window_plan", "reviewer_queue_population_plan", "hard_negative_sampling_plan",
            "expected_gold_value", "next_fetch_action"],
        "agent_cannot": [
            "provider secret 추측/생성", "같은 사건 확정", "merge 실행", "public Intelligence Unit 생성",
            "community reaction 을 event anchor 로 사용", "market/catalog 를 event anchor 로 사용"],
        "provider_readiness": {
            "query_capable": readiness["query_capable_providers"],
            "key_free_ready": readiness["key_free_ready"],
            "key_required_missing": readiness["key_required_missing"],
            "blocked": readiness["provider_blocked"],
            "unknown": readiness["provider_unknown"],
            "next_actions": readiness["next_actions"],
        },
        "live_query": {
            "allowed": live["live_query_allowed"], "attempted": live["live_query_attempted"],
            "candidate_count": live["candidate_count"],
            "reviewer_queue_population_count": live["reviewer_queue_population_count"],
            "block_reasons": live["block_reasons"], "dataset_source": live["dataset_source"],
        },
        "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go(이번 턴 호출 0).
        "no_secret_fabrication": True,
        "no_merge_without_gate": True,
        "no_public_intelligence_unit": True,
        "llm_invoked": False,
    }


# ── 최상위 orchestrator(옵션 A+B+D 통합 — §4 필수 output 단일 dict) ─────────────────────────────────────
def run_provider_acquisition_readiness(
    *, provider: str = "gdelt", topic: str = "central bank rate decision",
    topic_key: str = "central_bank_rate", time_window: str = "1d",
    source_ids: Optional[list[str]] = None, live_query: bool = False,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    rss_transport: Optional[Callable[[str, str], Optional[str]]] = None,
    gdelt_transport: Optional[Callable[[str], Optional[str]]] = None,
    host_gate: Any = None, reviewers: Optional[list[str]] = None,
) -> dict:
    """ADR#61 단일 진입 — provider readiness(A) → optional live query(B) → near-match queue population(D).

    기본 live_query=False → readiness report 만(network 0). provider 가 안전·허용 + opt-in 이면 bounded live query
    를 시도하고 후보를 queue 로 연결한다. 병합·LLM·운영 DB 0. §4 필수 output 을 단일 dict 로 산출."""
    readiness = build_provider_readiness_report(
        env_status_fn=env_status_fn, host_gate=host_gate)
    live = run_optional_live_query(
        provider=provider, topic=topic, topic_key=topic_key, time_window=time_window,
        source_ids=source_ids, live_query=live_query, readiness=readiness,
        env_status_fn=env_status_fn, rss_transport=rss_transport, gdelt_transport=gdelt_transport,
        host_gate=host_gate, reviewers=reviewers)
    agent_schema = build_provider_readiness_agent_schema(readiness, live)
    return {
        "provider_readiness_report": readiness,
        "query_capable_providers": readiness["query_capable_providers"],
        "key_free_ready": readiness["key_free_ready"],
        "key_required_missing": readiness["key_required_missing"],
        "provider_blocked": readiness["provider_blocked"],
        "provider_unknown": readiness["provider_unknown"],
        "env_var_requirements": readiness["env_var_requirements"],
        "rate_limit_policy": readiness["rate_limit_policy"],
        "host_gate_status": readiness["host_gate_status"],
        "credential_status": readiness["credential_status"],
        "live_query_allowed": live["live_query_allowed"],
        "live_query_attempted": live["live_query_attempted"],
        "live_query_result": live["live_query_result"],
        "candidate_count": live["candidate_count"],
        "near_match_count": live["near_match_count"],
        "reviewer_queue_population_count": live["reviewer_queue_population_count"],
        "dataset_source": live["dataset_source"],
        "provenance": live["provenance"],
        "block_reasons": live["block_reasons"],
        "next_actions": readiness["next_actions"],
        "agent_schema": agent_schema,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
    }


# ── CLI(기본 readiness report·network 0; --live-query 로 opt-in bounded live query) ─────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("query-capable provider acquisition readiness gate (ADR#61·병합 0·LLM 0·DB write 0; "
                     "기본 readiness report·network 0; --live-query 로 opt-in bounded governed fetch)."))
    parser.add_argument("--provider", default="gdelt",
                        help="optional live query provider(기본 gdelt). readiness report 는 항상 전체.")
    parser.add_argument("--topic", default="central bank rate decision", help="targeted topic(수집 의도).")
    parser.add_argument("--time-window", default="1d", help="time window(1d/7d).")
    parser.add_argument("--live-query", action="store_true",
                        help="실 governed fetch opt-in(network·CI 아님). safe_to_live_query + credentials 필요.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    host_gate = None
    if ns.live_query and ns.provider == "rss_fleet":
        try:
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None

    out = run_provider_acquisition_readiness(
        provider=ns.provider, topic=ns.topic, time_window=ns.time_window,
        live_query=ns.live_query, host_gate=host_gate)
    rep = out["provider_readiness_report"]
    print("- provider readiness (query-capable provider acquisition gate · ADR#61):")
    for r in rep["providers"]:
        print(f"    {r['provider_id']:<20} {r['classification']:<24} "
              f"cred_ready={r['credential_ready']!s:<5} safe={r['safe_to_live_query']!s:<5} "
              f"-> {r['next_action']}")
    print(f"- query_capable={out['query_capable_providers']}")
    print(f"- key_free_ready={out['key_free_ready']} key_required_missing={out['key_required_missing']}")
    print(f"- provider_blocked={out['provider_blocked']} provider_unknown={out['provider_unknown']}")
    print(f"- live_query: allowed={out['live_query_allowed']} attempted={out['live_query_attempted']} "
          f"candidate_count={out['candidate_count']} queue_population={out['reviewer_queue_population_count']} "
          f"dataset_source={out['dataset_source']}")
    print(f"- block_reasons={out['block_reasons']}")
    print(f"- merge_allowed=False no_public_IU={out['no_public_intelligence_unit']} "
          f"embedding_adjudicator={out['agent_schema']['embedding_llm_adjudicator']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
