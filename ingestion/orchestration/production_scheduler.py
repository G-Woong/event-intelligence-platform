"""Phase F-2 Periodic Scheduler / Run Planner — 모든 정책을 하나의 run plan으로 통합.

scheduler는 다음을 한 번에 결합한다:
  source_profiles(interval/freshness) → ProductionSourceState → SourceStrategyMemory
  → RateLimitGovernor(쿨다운/간격) → quarantine(state.quarantine_until) → dead-end skip
  → cycle_planner.is_due

결과 ProductionRunPlan은 due source와 skip source(+사유)를 명확히 분리한다. due가 아닌
source는 "alive인데 빠뜨림"이 아니라 명시적 skip 사유를 갖는다.

모드:
  - production: due source만(interval 준수)
  - production-validation: schedulable 전체를 강제 due(--all-due, 단 정책/쿨다운/격리 skip은 유지)
  - audit: E-1/E-2 감사용(별도 runner가 소비) — interval 무시

stdlib만. 신규 설치 0. 네트워크 0(순수 계획 함수).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ingestion.orchestration.cycle_planner import is_due
from ingestion.orchestration.production_state import (
    ProductionSourceState,
    decide_production_strategy,
)
from ingestion.orchestration.quarantine import is_quarantine_active

MODE_PRODUCTION = "production"
MODE_VALIDATION = "production-validation"
MODE_DRY_RUN = "production-dry-run"
MODE_AUDIT = "audit"


@dataclass(frozen=True)
class ProductionRunPlan:
    run_id: str
    created_at: str
    due_sources: tuple[str, ...]
    skipped_sources: tuple[str, ...]
    skipped_reasons: dict[str, str]
    expected_calls: int
    strategy_by_source: dict[str, str]
    mode: str
    skip_category_counts: dict[str, int] = field(default_factory=dict)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _skip_category(reason: str) -> str:
    """skip 사유 → 카테고리(모니터링 집계용)."""
    if reason.startswith("policy_excluded"):
        return "skipped_policy"
    if reason.startswith("dead_end"):
        # rate-limited 상태가 dead_end로 새지 않게 하되, 정책 차단/미서비스는 dead_end로 집계
        return "skipped_dead_end"
    if reason.startswith("quarantine"):
        return "skipped_quarantine"
    # rate-limited / cooldown / 외부 쿨다운 상태 → cooldown 집계
    if (reason.startswith("cooldown") or reason.startswith("rate_limit")
            or "min_interval" in reason or "EXTERNAL_RATE_LIMITED" in reason
            or "COOLDOWN" in reason):
        return "skipped_cooldown"
    if reason.startswith("not_due"):
        return "skipped_not_due"
    if reason.startswith("not_ready"):
        return "skipped_not_ready"
    return "skipped_other"


def build_production_run_plan(
    profiles,
    *,
    states: dict[str, ProductionSourceState],
    memory: Optional[dict] = None,
    last_run_at_by_source: Optional[dict[str, datetime]] = None,
    governor=None,
    now: Optional[datetime] = None,
    mode: str = MODE_PRODUCTION,
    max_sources: Optional[int] = None,
    run_id: str = "",
) -> ProductionRunPlan:
    """profile 목록 + 상태/메모리/거버너 → ProductionRunPlan.

    skip 우선순위: excluded > dead-end/not-ready(state) > quarantine > cooldown(state) >
    governor(쿨다운/간격) > not_due(interval). validation 모드는 interval skip을 면제하되
    정책/격리/쿨다운 skip은 유지한다(우회 금지).
    """
    now = now or datetime.now(timezone.utc)
    memory = memory or {}
    last_run = last_run_at_by_source or {}
    due: list[str] = []
    skipped: list[str] = []
    reasons: dict[str, str] = {}
    strategy_by_source: dict[str, str] = {}

    for profile in profiles:
        sid = profile.source_id
        state = states.get(sid)

        # 0) 상태 없음 — 운영 불가(상위 runner가 모든 source 상태를 보장해야 함)
        if state is None:
            skipped.append(sid)
            reasons[sid] = "no_state"
            continue

        # 1) excluded
        if not profile.enabled or state.excluded:
            skipped.append(sid)
            reasons[sid] = f"policy_excluded:{state.terminal_reason or 'excluded'}"
            continue

        # 2) dead-end / not-ready (전략 결정에 위임)
        decision = decide_production_strategy(sid, profile, memory, state)
        if decision.skip:
            skipped.append(sid)
            reasons[sid] = decision.skip_reason or f"not_ready:{state.current_status}"
            continue

        # 3) quarantine 활성
        if is_quarantine_active(state.quarantine_until, now=now):
            skipped.append(sid)
            reasons[sid] = f"quarantine_until:{state.quarantine_until}"
            continue

        # 4) state cooldown 활성
        cd = _parse_iso(state.cooldown_until)
        if cd is not None and cd > now:
            skipped.append(sid)
            reasons[sid] = f"cooldown_until:{state.cooldown_until}"
            continue

        min_interval = int(getattr(profile, "min_interval_seconds", 1800))

        # 5) governor(쿨다운/min_interval)
        if governor is not None:
            g = governor.decide(sid, min_interval_seconds=min_interval, now=now)
            if not g.allowed:
                skipped.append(sid)
                reasons[sid] = g.reason or "rate_limit_skip"
                continue

        # 6) interval due 판정 (validation 모드는 강제 due)
        if mode != MODE_VALIDATION:
            lr = last_run.get(sid)
            if not is_due(now, lr, min_interval):
                skipped.append(sid)
                reasons[sid] = f"not_due:interval_{min_interval}s"
                continue

        # → due
        due.append(sid)
        if decision.strategy:
            strategy_by_source[sid] = decision.strategy

    # max_sources 제한(초과분은 deferred로 skip)
    if max_sources is not None and len(due) > max_sources:
        overflow = due[max_sources:]
        due = due[:max_sources]
        for sid in overflow:
            skipped.append(sid)
            reasons[sid] = "deferred:max_sources_cap"

    cat_counts: dict[str, int] = {}
    for sid in skipped:
        cat = _skip_category(reasons.get(sid, ""))
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    return ProductionRunPlan(
        run_id=run_id,
        created_at=now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        due_sources=tuple(due),
        skipped_sources=tuple(skipped),
        skipped_reasons=reasons,
        expected_calls=len(due),
        strategy_by_source=strategy_by_source,
        mode=mode,
        skip_category_counts=cat_counts,
    )
