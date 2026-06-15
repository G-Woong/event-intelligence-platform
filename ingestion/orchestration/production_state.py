"""Phase F-1 ProductionSourceState — 모든 non-excluded source의 운영 상태 모델.

설계 07(orchestration architecture) + 08(retry/rate-limit/quarantine) + E-3 strategy memory를
결합해 각 source가 **최종 운영 상태(production state)** 를 갖도록 한다. UNKNOWN은 0이어야 한다:
derive_production_state는 total function — 어떤 입력이든 구체 enum을 돌려준다.

입력 3종을 결합한다:
  1. SourceProfile (enabled/excluded/skip_reason/requires_api_key/live_eligible/group)
  2. SourceStrategyMemory (E-3 학습 final_status/successful_strategy/dead_end)
  3. SourceHealthState (런타임 cooldown/quarantine/terminal — 선택)

원칙: 살아난(memory data_alive) source는 PRODUCTION_READY, 종결(terminal) source는 그
종결 사유에 맞는 운영 상태로 둔다. health가 런타임에 cooldown/quarantine을 걸면 그것이
정적 상태를 덮는다(런타임 우선). 키 미보유로 못 도는 source는 NEEDS_OPERATOR_REVIEW —
이것도 UNKNOWN이 아니라 명시적 최종 상태다.

stdlib + yaml/json. 신규 설치 0.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from ingestion.orchestration.full_source_revival import (
    DATA_ALIVE_STATUSES,
)
from ingestion.orchestration.source_strategy_memory import (
    SourceStrategyMemory,
    is_known_dead_end,
    preferred_strategy_for,
)

# ── production state enum ────────────────────────────────────────────────────
PRODUCTION_READY = "PRODUCTION_READY"
PRODUCTION_READY_DEGRADED = "PRODUCTION_READY_DEGRADED"
POLICY_EXCLUDED = "POLICY_EXCLUDED"
POLICY_BLOCKED_NO_BYPASS = "POLICY_BLOCKED_NO_BYPASS"
EXTERNAL_RATE_LIMITED = "EXTERNAL_RATE_LIMITED"
EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
VENDOR_CONTRACT_REQUIRED = "VENDOR_CONTRACT_REQUIRED"
NOT_SERVICE_USEFUL = "NOT_SERVICE_USEFUL"
QUARANTINED = "QUARANTINED"
COOLDOWN = "COOLDOWN"
DEAD_END_SKIPPED = "DEAD_END_SKIPPED"
NEEDS_OPERATOR_REVIEW = "NEEDS_OPERATOR_REVIEW"
UNKNOWN = "UNKNOWN"

PRODUCTION_STATES: frozenset[str] = frozenset({
    PRODUCTION_READY, PRODUCTION_READY_DEGRADED, POLICY_EXCLUDED,
    POLICY_BLOCKED_NO_BYPASS, EXTERNAL_RATE_LIMITED, EXTERNAL_API_ERROR,
    VENDOR_CONTRACT_REQUIRED, NOT_SERVICE_USEFUL, QUARANTINED, COOLDOWN,
    DEAD_END_SKIPPED, NEEDS_OPERATOR_REVIEW, UNKNOWN,
})

# scheduler가 due 후보로 삼는 상태 (실행 가능)
SCHEDULABLE_STATES: frozenset[str] = frozenset({
    PRODUCTION_READY, PRODUCTION_READY_DEGRADED,
})
# 영구 skip (dead-end) — 운영 plan에서 제외, profiles에는 유지
DEAD_END_STATES: frozenset[str] = frozenset({
    POLICY_EXCLUDED, POLICY_BLOCKED_NO_BYPASS, NOT_SERVICE_USEFUL, DEAD_END_SKIPPED,
})
# 조건부 skip — operator/외부/쿨다운 해소 시 재개 가능
CONDITIONAL_SKIP_STATES: frozenset[str] = frozenset({
    EXTERNAL_RATE_LIMITED, EXTERNAL_API_ERROR, VENDOR_CONTRACT_REQUIRED,
    QUARANTINED, COOLDOWN, NEEDS_OPERATOR_REVIEW,
})

# E-3 terminal final_status → production state 매핑
_FINAL_STATUS_TO_STATE = {
    "EXTERNAL_RATE_LIMITED_WITH_RETRY_POLICY": EXTERNAL_RATE_LIMITED,
    # Phase G-2: pending_resume는 fresh data 0건 → READY로 둔갑 금지(정직한 rate-limit 홀드오버).
    "EXTERNAL_RATE_LIMITED_PENDING_RESUME": EXTERNAL_RATE_LIMITED,
    "EXTERNAL_RATE_LIMITED": EXTERNAL_RATE_LIMITED,
    # Phase G-2: 공식 API/계약 필요(google_trends_explore) — vendor contract 등급으로 매핑.
    "REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT": VENDOR_CONTRACT_REQUIRED,
    "EXTERNAL_API_ERROR_WITH_EVIDENCE": EXTERNAL_API_ERROR,
    "EXTERNAL_API_ERROR": EXTERNAL_API_ERROR,
    "REQUIRES_VENDOR_SPECIFIC_API_CONTRACT": VENDOR_CONTRACT_REQUIRED,
    "REQUIRES_TWO_STEP_DETAIL_FETCH": VENDOR_CONTRACT_REQUIRED,
    "NOT_SERVICE_USEFUL": NOT_SERVICE_USEFUL,
    "DISABLE_RECOMMENDED": NOT_SERVICE_USEFUL,
    "POLICY_BLOCKED_NO_BYPASS": POLICY_BLOCKED_NO_BYPASS,
    "PAYWALL_BLOCKED_NO_BYPASS": POLICY_BLOCKED_NO_BYPASS,
    "LOGIN_BLOCKED_NO_BYPASS": POLICY_BLOCKED_NO_BYPASS,
    "CAPTCHA_BLOCKED_NO_BYPASS": POLICY_BLOCKED_NO_BYPASS,
    "ROBOTS_BLOCKED_NO_BYPASS": POLICY_BLOCKED_NO_BYPASS,
    "TOOL_UNAVAILABLE_FOR_REQUIRED_STRATEGY": NEEDS_OPERATOR_REVIEW,
    "BLOCKED_ENV_KEY": NEEDS_OPERATOR_REVIEW,
    "EXCLUDED_BY_USER": POLICY_EXCLUDED,
}

# skip_reason(profile) → production state (memory 없는 source용)
_SKIP_REASON_TO_STATE = {
    "robots_or_policy_block": POLICY_BLOCKED_NO_BYPASS,
    "login_wall_no_bypass": POLICY_BLOCKED_NO_BYPASS,
    "paywall_no_bypass": POLICY_BLOCKED_NO_BYPASS,
    "captcha_no_bypass": POLICY_BLOCKED_NO_BYPASS,
    "disabled_by_policy": POLICY_EXCLUDED,
    "needs_api_integration": VENDOR_CONTRACT_REQUIRED,
    "requires_api_key": NEEDS_OPERATOR_REVIEW,   # 키 보유 시 PRODUCTION_READY로 승격(아래 처리)
    "user_excluded": POLICY_EXCLUDED,
}

# health state → production state (런타임 우선)
_HEALTH_TO_STATE = {
    "QUARANTINED_RETRYABLE": QUARANTINED,
    "RATE_LIMITED_COOLDOWN": COOLDOWN,
    "BLOCKED_TERMINAL": POLICY_BLOCKED_NO_BYPASS,
}

# group → 기대 alive 타입(보고/모니터링용)
_EXPECTED_ALIVE_BY_GROUP = {
    "news": "ARTICLE_BODY_ALIVE",
    "community": "COMMUNITY_SIGNAL_ALIVE",
    "search": "SEARCH_RESULT_ALIVE",
    "official": "OFFICIAL_RECORD_ALIVE",
    "trend": "STRUCTURED_SIGNAL_ALIVE",
    "market": "STRUCTURED_SIGNAL_ALIVE",
    "domain": "OFFICIAL_RECORD_ALIVE",
}


@dataclass(frozen=True)
class ProductionSourceState:
    source_id: str
    enabled: bool
    excluded: bool
    source_group: str
    expected_alive_type: str
    current_status: str
    last_success_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    failure_count: int = 0
    consecutive_failure_count: int = 0
    quarantine_until: Optional[str] = None
    cooldown_until: Optional[str] = None
    known_dead_end: bool = False
    best_strategy: Optional[str] = None
    next_strategy: Optional[str] = None
    next_due_at: Optional[str] = None
    rate_limit_status: Optional[str] = None
    production_ready: bool = False
    terminal_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProductionSourceState":
        fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in fields})


@dataclass(frozen=True)
class ProductionStrategyDecision:
    """F-5/F-6: production runner가 source별로 어떤 전략을 쓰고 skip할지."""
    source_id: str
    strategy: Optional[str]
    skip: bool
    skip_reason: Optional[str]
    dead_end: bool


def derive_production_state(
    profile,
    *,
    memory: Optional[dict] = None,
    health=None,
    api_key_ready: Optional[bool] = None,
    last_success_at: Optional[str] = None,
    last_failure_at: Optional[str] = None,
    failure_count: int = 0,
    consecutive_failure_count: int = 0,
) -> ProductionSourceState:
    """profile + memory + health → ProductionSourceState (total function, UNKNOWN 회피).

    우선순위: excluded > 런타임 health(quarantine/cooldown/terminal) > memory final_status
    > skip_reason/live_eligible 기반 정적 추론. memory의 successful_strategy를 best_strategy로
    싣고, dead-end면 known_dead_end=True.
    """
    sid = profile.source_id
    grp = (getattr(profile, "source_group", None) or getattr(profile, "purpose", None) or "news")
    expected = _EXPECTED_ALIVE_BY_GROUP.get(grp, "ARTICLE_BODY_ALIVE")
    mem: Optional[SourceStrategyMemory] = (memory or {}).get(sid)
    best = preferred_strategy_for(sid, memory or {})
    next_strat = best or getattr(profile, "preferred_strategy", None)
    dead_end = is_known_dead_end(sid, memory or {}) if memory else False

    base = dict(
        source_id=sid, enabled=bool(profile.enabled),
        excluded=not bool(profile.enabled), source_group=grp,
        expected_alive_type=expected, last_success_at=last_success_at,
        last_failure_at=last_failure_at, failure_count=failure_count,
        consecutive_failure_count=consecutive_failure_count,
        best_strategy=best, next_strategy=next_strat,
    )

    # 1) excluded (enabled=false) — 영구 정책 제외
    if not profile.enabled:
        return ProductionSourceState(
            current_status=POLICY_EXCLUDED, production_ready=False,
            known_dead_end=True, terminal_reason=getattr(profile, "skip_reason", None) or "excluded",
            **base,
        )

    # 2) 런타임 health 우선 (cooldown/quarantine/terminal)
    if health is not None:
        hstate = _HEALTH_TO_STATE.get(getattr(health, "state", None))
        if hstate is not None:
            return ProductionSourceState(
                current_status=hstate,
                production_ready=False,
                known_dead_end=(hstate == POLICY_BLOCKED_NO_BYPASS),
                quarantine_until=getattr(health, "next_retry_at", None) if hstate == QUARANTINED else None,
                cooldown_until=getattr(health, "next_retry_at", None) if hstate == COOLDOWN else None,
                rate_limit_status=("cooldown" if hstate == COOLDOWN else None),
                terminal_reason=getattr(health, "reason", None),
                **base,
            )

    # 3) memory 학습 final_status
    if mem is not None:
        fs = mem.final_status
        if fs in DATA_ALIVE_STATUSES:
            degraded = bool(mem.root_cause_after)  # NO_STABLE_URL/NO_TIMESTAMP 등 → degraded
            return ProductionSourceState(
                current_status=(PRODUCTION_READY_DEGRADED if degraded else PRODUCTION_READY),
                production_ready=True, known_dead_end=False,
                terminal_reason=(";".join(mem.root_cause_after) if degraded else None),
                **base,
            )
        mapped = _FINAL_STATUS_TO_STATE.get(fs)
        if mapped is not None:
            return ProductionSourceState(
                current_status=mapped, production_ready=False,
                known_dead_end=(mapped in DEAD_END_STATES),
                rate_limit_status=("rate_limited" if mapped == EXTERNAL_RATE_LIMITED else None),
                terminal_reason=(";".join(mem.root_cause_after) or fs),
                **base,
            )

    # 4) static 추론 (memory 없는 E-2 data_alive / 키 필요 source)
    skip_reason = getattr(profile, "skip_reason", None)
    live = getattr(profile, "live_eligible", "false")

    if skip_reason == "requires_api_key":
        if api_key_ready:
            return ProductionSourceState(
                current_status=PRODUCTION_READY, production_ready=True,
                known_dead_end=False, **base,
            )
        return ProductionSourceState(
            current_status=NEEDS_OPERATOR_REVIEW, production_ready=False,
            known_dead_end=False, terminal_reason="api_key_missing", **base,
        )

    mapped = _SKIP_REASON_TO_STATE.get(skip_reason) if skip_reason else None
    if mapped is not None:
        return ProductionSourceState(
            current_status=mapped, production_ready=(mapped == PRODUCTION_READY),
            known_dead_end=(mapped in DEAD_END_STATES),
            terminal_reason=skip_reason, **base,
        )

    # 키 불필요 + 블로커 없음 → E-2에서 alive 검증된 source로 간주
    if live in ("true", "conservative"):
        return ProductionSourceState(
            current_status=PRODUCTION_READY, production_ready=True,
            known_dead_end=False, **base,
        )

    # live_eligible=false 인데 skip_reason도 없음 — 검토 필요(UNKNOWN 아님)
    return ProductionSourceState(
        current_status=NEEDS_OPERATOR_REVIEW, production_ready=False,
        known_dead_end=False, terminal_reason="not_live_eligible_no_reason", **base,
    )


def decide_production_strategy(
    source_id: str,
    profile,
    memory: Optional[dict],
    state: Optional[ProductionSourceState],
) -> ProductionStrategyDecision:
    """F-5/F-6: 성공 전략 재사용 + dead-end skip + failed 전략 회피.

    - state.known_dead_end 또는 dead-end final_status → skip(dead_end)
    - memory의 successful_strategy/preferred_next_strategy 우선
    - 없으면 profile.preferred_strategy fallback
    """
    mem_dict = memory or {}
    # state가 있으면 F-1의 세분화된 의미를 신뢰한다(coarse is_known_dead_end로 rate-limited를
    # 영구 dead-end로 오분류하지 않는다). state가 없을 때만 memory 휴리스틱으로 fallback.
    if state is not None:
        if state.known_dead_end:
            return ProductionStrategyDecision(
                source_id=source_id, strategy=None, skip=True,
                skip_reason=f"dead_end:{state.current_status}", dead_end=True,
            )
        if not state.production_ready:
            return ProductionStrategyDecision(
                source_id=source_id, strategy=state.next_strategy, skip=True,
                skip_reason=f"not_ready:{state.current_status}", dead_end=False,
            )
    elif is_known_dead_end(source_id, mem_dict):
        return ProductionStrategyDecision(
            source_id=source_id, strategy=None, skip=True,
            skip_reason="dead_end:memory", dead_end=True,
        )
    strat = preferred_strategy_for(source_id, mem_dict) or getattr(profile, "preferred_strategy", None)
    return ProductionStrategyDecision(
        source_id=source_id, strategy=strat, skip=False, skip_reason=None, dead_end=False,
    )


# ── persistence (gitignored outputs) ─────────────────────────────────────────
_DEFAULT_STATE_PATH = (
    Path(__file__).parent.parent / "outputs" / "state" / "production_source_state.json"
)


def save_production_state(
    states: list[ProductionSourceState],
    path: str | Path | None = None,
    *,
    run_id: Optional[str] = None,
) -> Path:
    """ProductionSourceState 목록을 JSON으로 원자적 저장(gitignored). secret 없음."""
    p = Path(path) if path else _DEFAULT_STATE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "sources": {s.source_id: s.to_dict() for s in sorted(states, key=lambda x: x.source_id)},
    }
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    try:
        os.replace(tmp, p)
    except PermissionError:
        time.sleep(0.1)
        os.replace(tmp, p)
    return p


def load_production_state(path: str | Path | None = None) -> dict[str, ProductionSourceState]:
    """저장된 production state 로드 → {source_id: ProductionSourceState}. 없으면 {}."""
    p = Path(path) if path else _DEFAULT_STATE_PATH
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, ProductionSourceState] = {}
    for sid, entry in (raw.get("sources") or {}).items():
        if isinstance(entry, dict):
            out[sid] = ProductionSourceState.from_dict(entry)
    return out


def summarize_states(states) -> dict:
    """production state 분포 집계(모니터링/보고용). source_without_state 검출 포함."""
    states = list(states)
    dist: dict[str, int] = {}
    without_state = 0
    for s in states:
        st = s.current_status
        if st not in PRODUCTION_STATES or st == UNKNOWN:
            without_state += 1
        dist[st] = dist.get(st, 0) + 1
    return {
        "total": len(states),
        "distribution": dict(sorted(dist.items())),
        "production_ready": dist.get(PRODUCTION_READY, 0) + dist.get(PRODUCTION_READY_DEGRADED, 0),
        "source_without_state": without_state,
        "unknown": dist.get(UNKNOWN, 0),
    }
