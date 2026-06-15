"""Phase G2-10 gdelt rescue strategy — rate-limit 무시가 아니라 '정책 준수 + 재개'로 흡수.

조사로 확인된 사실:
- gdelt는 공개 DOC 2.0 API(키 불필요)로 실제 수집되어 왔다(outputs/extracted_payload/gdelt 다수).
- 단발 호출이 종종 429("one every 5 seconds")를 받는다 = provider rate-limit governance 문제.

이 전략:
- 호출 전 RateLimitGovernor로 min_interval/cooldown을 강제(쿨다운 중이면 호출 안 함).
- query를 점진적으로 단순화(broad → keyword → narrow)하며 정책 간격을 두고 최대 N회 probe.
- 429면 cooldown_until을 저장하고 EXTERNAL_RATE_LIMITED_PENDING_RESUME(terminal 아님 → 다음 run 자동 재개).
- 성공하면 OFFICIAL_RECORD_ALIVE + records(EventQueue 적재 가능).

기존 RateLimitGovernor / vendor_api_routes.fetch_gdelt 재사용. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.orchestration.vendor_api_routes import VendorRouteResult, fetch_gdelt

# query 단순화 ladder: (label, query, limit, timespan). exotic 연산자 없이 안전한 키워드만.
_DEFAULT_LADDER: tuple[tuple[str, str, int, str], ...] = (
    ("broad", "climate OR economy OR election", 5, "1d"),
    ("single_keyword", "economy", 3, "6h"),
    ("narrow", "election", 1, "1h"),
)


@dataclass(frozen=True)
class GdeltStrategyResult:
    source_id: str
    success: bool
    status_code: Optional[int]
    records: tuple[dict, ...]
    item_count: int
    attempts: tuple[str, ...]
    final_status: str
    cooldown_until: Optional[str]
    next_resume_at: Optional[str]
    error: Optional[str]


def collect_gdelt(
    *,
    governor: RateLimitGovernor,
    vendor_fetch: Callable[..., VendorRouteResult] = fetch_gdelt,
    min_interval_seconds: int = 10,
    max_probes: int = 3,
    now: Optional[datetime] = None,
    sleep: Optional[Callable[[float], None]] = None,
    ladder: tuple[tuple[str, str, int, str], ...] = _DEFAULT_LADDER,
) -> GdeltStrategyResult:
    """정책 준수 spaced probe로 gdelt를 수집. 429면 pending_resume(자동 재개) state.

    sleep는 주입형(테스트=no-op). 쿨다운 중이면 네트워크 호출 없이 즉시 pending_resume.
    """
    # 1) 쿨다운/간격 검사 — 막혀 있으면 호출하지 않는다(no tight-loop)
    decision = governor.decide("gdelt", min_interval_seconds=min_interval_seconds, now=now)
    if not decision.allowed:
        return GdeltStrategyResult(
            "gdelt", False, None, (), 0, (), "EXTERNAL_RATE_LIMITED_PENDING_RESUME",
            decision.cooldown_until, decision.cooldown_until, decision.reason)

    attempts: list[str] = []
    last_status: Optional[int] = None
    last_error: Optional[str] = None
    for i, (label, query, limit, timespan) in enumerate(ladder[:max_probes]):
        if i > 0 and sleep is not None:
            sleep(min_interval_seconds)          # 정책 간격(테스트=no-op)
        governor.record_call("gdelt", now=now)
        res = vendor_fetch(query=query, limit=limit, timespan=timespan)
        attempts.append(label)
        last_status = res.status_code
        last_error = res.error
        if res.success and res.records:
            return GdeltStrategyResult(
                "gdelt", True, res.status_code, res.records, res.item_count,
                tuple(attempts), "OFFICIAL_RECORD_ALIVE", None, None, None)
        # 429/provider rate-limit → cooldown 저장 후 즉시 pending_resume(terminal 아님)
        if res.status_code == 429 or res.error == "provider_rate_limited":
            cd = governor.record_rate_limited(
                "gdelt", freshness_bucket="near_real_time",
                reason="gdelt_provider_429", now=now)
            return GdeltStrategyResult(
                "gdelt", False, res.status_code, (), 0, tuple(attempts),
                "EXTERNAL_RATE_LIMITED_PENDING_RESUME", cd, cd, "provider_rate_limited")
        # 그 외(200 OK but no articles / http error): 다음 단순 query 시도
    # ladder 소진 — 정직한 holdover로 짧은 cooldown 저장 후 다음 run 재개
    cd = governor.record_rate_limited(
        "gdelt", freshness_bucket="near_real_time",
        reason=f"gdelt_no_records:{last_error}", now=now)
    return GdeltStrategyResult(
        "gdelt", False, last_status, (), 0, tuple(attempts),
        "EXTERNAL_RATE_LIMITED_PENDING_RESUME", cd, cd, last_error or "no_records")
