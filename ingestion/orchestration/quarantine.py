"""Phase F-4 Failure Quarantine — 반복 실패 source 격리 정책.

설계 08의 quarantine 정책을 운영 결정으로 구체화한다. ``ingestion/core/source_health``의
상태 머신(apply_probe_outcome/should_skip)이 실제 누적/전이를 담당하고, 이 모듈은 그 위에서
**QuarantineDecision**(격리 여부 + recovery 전략 + operator review 필요성)을 산출한다.

정책:
  - 정책 terminal(PAYWALL/LOGIN/CAPTCHA/ROBOTS) → 즉시 policy terminal(격리 아님, dead-end).
  - EXTERNAL_API_ERROR/네트워크 실패 연속 N회(기본 3) → quarantine(재시도 가능, 쿨다운 후 probe).
  - BODY_FETCH_FAILED 반복 → 다른 전략 시도 권고 후 임계 도달 시 quarantine.
  - NOT_SERVICE_USEFUL → dead-end skip(격리 아님).
  - VENDOR_CONTRACT_REQUIRED → operator action 필요(격리 아님, NEEDS_OPERATOR_REVIEW).

stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# 즉시 정책 종결(격리가 아니라 dead-end) — 우회 금지
_POLICY_TERMINAL_CATEGORIES = frozenset({
    "CAPTCHA_DETECTED", "LOGIN_WALL_DETECTED", "PAYWALL_DETECTED",
    "ROBOTS_BLOCKED", "LOGIN_WALL", "LICENSE_REQUIRED",
})
# 누적 시 quarantine 대상이 되는 실패 카테고리/상태
_RETRYABLE_FAILURE = frozenset({
    "NETWORK_ERROR", "TIMEOUT", "EXTERNAL_API_ERROR", "HTTP_5XX",
    "NETWORK_TIMEOUT", "NETWORK_CONNECTION_RESET", "FETCH_ERROR",
})
_BODY_FETCH_FAILURE = frozenset({"BODY_FETCH_FAILED", "NO_BODY", "EXCERPT_ONLY"})

_DEFAULT_QUARANTINE_THRESHOLD = 3
_QUARANTINE_RECHECK_SECONDS = 6 * 3600


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class QuarantineDecision:
    source_id: str
    quarantined: bool
    quarantine_until: Optional[str]
    reason: Optional[str]
    recovery_strategy: Optional[str]


def evaluate_quarantine(
    source_id: str,
    *,
    last_status: Optional[str] = None,
    error_category: Optional[str] = None,
    consecutive_failure_count: int = 0,
    quarantine_threshold: int = _DEFAULT_QUARANTINE_THRESHOLD,
    body_fetch_failures: int = 0,
    alternative_strategy_available: bool = False,
    now: Optional[datetime] = None,
) -> QuarantineDecision:
    """source의 누적 실패 상황 → QuarantineDecision.

    정책 terminal은 격리가 아니라 즉시 종결(quarantined=False, reason=policy_terminal)로
    반환한다(상위에서 POLICY_BLOCKED_NO_BYPASS로 분류). 재시도 가능 실패만 임계 누적 시
    quarantine한다. body fetch 반복 실패는 먼저 대체 전략을 권고한다.
    """
    now = now or datetime.now(timezone.utc)
    cat = (error_category or "").upper()
    status = (last_status or "").upper()

    # 1) 정책 terminal — 즉시 종결, 격리 아님
    if cat in _POLICY_TERMINAL_CATEGORIES or status in (
        "PAYWALL_BLOCKED_NO_BYPASS", "LOGIN_BLOCKED_NO_BYPASS",
        "CAPTCHA_BLOCKED_NO_BYPASS", "ROBOTS_BLOCKED_NO_BYPASS", "BLOCKED",
    ):
        return QuarantineDecision(
            source_id=source_id, quarantined=False, quarantine_until=None,
            reason=f"policy_terminal:{cat or status}", recovery_strategy=None,
        )

    # 2) NOT_SERVICE_USEFUL / vendor contract — 격리 아님(상위에서 dead-end/operator)
    if status in ("NOT_SERVICE_USEFUL", "DISABLE_RECOMMENDED"):
        return QuarantineDecision(
            source_id=source_id, quarantined=False, quarantine_until=None,
            reason="not_service_useful", recovery_strategy=None,
        )
    if status in ("REQUIRES_VENDOR_SPECIFIC_API_CONTRACT", "REQUIRES_TWO_STEP_DETAIL_FETCH"):
        return QuarantineDecision(
            source_id=source_id, quarantined=False, quarantine_until=None,
            reason="vendor_contract_required", recovery_strategy="operator_configure_endpoint",
        )

    # 3) body fetch 반복 실패 — 임계 미만이면 대체 전략 권고, 임계 도달이면 quarantine
    if cat in _BODY_FETCH_FAILURE or status in _BODY_FETCH_FAILURE:
        if body_fetch_failures < quarantine_threshold and alternative_strategy_available:
            return QuarantineDecision(
                source_id=source_id, quarantined=False, quarantine_until=None,
                reason=f"body_fetch_retry_alt_strategy:{body_fetch_failures}",
                recovery_strategy="try_alternative_body_strategy",
            )
        if body_fetch_failures >= quarantine_threshold:
            until = _iso(now + timedelta(seconds=_QUARANTINE_RECHECK_SECONDS))
            return QuarantineDecision(
                source_id=source_id, quarantined=True, quarantine_until=until,
                reason=f"body_fetch_failed_repeated:{body_fetch_failures}",
                recovery_strategy="recheck_with_browser_after_cooldown",
            )

    # 4) 재시도 가능 실패 누적 → 임계 도달 시 quarantine
    if cat in _RETRYABLE_FAILURE or status in _RETRYABLE_FAILURE or status == "EXTERNAL_API_ERROR":
        if consecutive_failure_count >= quarantine_threshold:
            until = _iso(now + timedelta(seconds=_QUARANTINE_RECHECK_SECONDS))
            return QuarantineDecision(
                source_id=source_id, quarantined=True, quarantine_until=until,
                reason=f"consecutive_failures:{consecutive_failure_count}",
                recovery_strategy="recovery_probe_after_cooldown",
            )
        return QuarantineDecision(
            source_id=source_id, quarantined=False, quarantine_until=None,
            reason=f"transient_failure:{consecutive_failure_count}",
            recovery_strategy="retry_next_cycle",
        )

    # 5) 그 외 — 격리 없음
    return QuarantineDecision(
        source_id=source_id, quarantined=False, quarantine_until=None,
        reason=None, recovery_strategy=None,
    )


def is_quarantine_active(quarantine_until: Optional[str], *, now: Optional[datetime] = None) -> bool:
    """quarantine_until이 미래면 True(아직 격리 중 → skip)."""
    if not quarantine_until:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        deadline = datetime.fromisoformat(quarantine_until.replace("Z", "+00:00"))
    except ValueError:
        return False
    return deadline > now
