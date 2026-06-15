"""Phase G-3 FinalSourceClosure — 남은 비-excluded source(DEGRADED 3 + RATE_LIMITED 1) 종결.

source별 if-스파게티가 아니라 공통 파이프라인으로 흡수한다:
  SourceCapability → StrategyGraph → (executor가 만든) records → EvidenceGate → final_status.

final_status 결정은 단일 함수 decide_final_status로 통일한다(둔갑/과대평가 방지):
- records 0 + rate-limit → EXTERNAL_RATE_LIMITED_PENDING_RESUME (terminal 아님, 자동 재개)
- records 0 + 정책/구조 차단 + 증거 → VERIFIED_HARD_BLOCKER
- records 있고 EvidenceGate ready + 정책 caveat(HIGH 민감) → PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY(DEGRADED)
- records 있고 EvidenceGate ready + caveat 없음 → PRODUCTION_READY
- records 있으나 EvidenceGate not ready → NEEDS_OPERATOR_REVIEW(둔갑 금지)

네트워크 0, stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from ingestion.orchestration.source_capability import POLICY_HIGH, SourceCapability

# final_status enum
PRODUCTION_READY = "PRODUCTION_READY"
PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY = "PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY"
EXTERNAL_RATE_LIMITED_PENDING_RESUME = "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
VERIFIED_HARD_BLOCKER = "VERIFIED_HARD_BLOCKER"
NEEDS_OPERATOR_REVIEW = "NEEDS_OPERATOR_REVIEW"

# 데이터가 살아있는(수집됨) ready 계열 — preview_only는 DEGRADED지만 ready로 인정(실데이터 존재)
_READY_WITH_DATA = frozenset({PRODUCTION_READY, PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY})


@dataclass(frozen=True)
class FinalSourceClosure:
    source_id: str
    previous_status: str
    strategy_graph: tuple[str, ...]          # 실행한 전략 노드 이름들
    successful_strategy: Optional[str]
    failed_strategies: tuple[str, ...]
    live_records: int
    eventqueue_records: int
    raw_events_records: int
    final_status: str
    ready_or_degraded_reason: Optional[str]
    pending_resume_at: Optional[str]
    hard_blocker_evidence: Optional[str]
    evidence_gate: Optional[dict] = None

    def is_production_ready(self) -> bool:
        """clean READY(승격 완료) — preview-only DEGRADED는 제외."""
        return self.final_status == PRODUCTION_READY and self.eventqueue_records > 0

    def is_ready_with_data(self) -> bool:
        return self.final_status in _READY_WITH_DATA and self.eventqueue_records > 0

    def is_degraded(self) -> bool:
        return self.final_status == PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY

    def is_pending_resume(self) -> bool:
        return self.final_status == EXTERNAL_RATE_LIMITED_PENDING_RESUME

    def is_hard_blocker(self) -> bool:
        return self.final_status == VERIFIED_HARD_BLOCKER

    def to_dict(self) -> dict:
        return asdict(self)


def decide_final_status(
    *,
    capability: SourceCapability,
    gate: Optional[dict],
    record_count: int,
    rate_limited: bool = False,
    pending_resume_at: Optional[str] = None,
    caveats: tuple[str, ...] = (),
    hard_blocker_evidence: Optional[str] = None,
) -> tuple[str, Optional[str], Optional[str]]:
    """(final_status, ready_or_degraded_reason, hard_blocker_evidence) 산출 — 공통 결정 로직."""
    # 1) 데이터 0건
    if record_count <= 0:
        if rate_limited:
            return (EXTERNAL_RATE_LIMITED_PENDING_RESUME,
                    f"provider_rate_limited;resume_at={pending_resume_at}", None)
        if hard_blocker_evidence:
            return (VERIFIED_HARD_BLOCKER, None, hard_blocker_evidence)
        return (NEEDS_OPERATOR_REVIEW, "no_records_no_documented_blocker", None)

    # 2) 데이터 있으나 EvidenceGate 미통과 → 둔갑 금지(승격 불가)
    if gate is not None and not gate.get("ready_allowed", False):
        reason = "evidence_gate_failed:" + ",".join(gate.get("downgrade_reasons", ()))
        return (NEEDS_OPERATOR_REVIEW, reason, None)

    # 3) 데이터 있고 EvidenceGate 통과 — 정책 caveat가 있으면(HIGH 민감) preview-only DEGRADED
    if caveats and capability.policy_sensitivity == POLICY_HIGH:
        return (PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY, ";".join(caveats), None)
    if caveats:
        # HIGH가 아니어도 미해소 caveat가 남아있으면 정직하게 degraded
        return (PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY, ";".join(caveats), None)
    return (PRODUCTION_READY, "live_records_with_real_evidence", None)


def classify_final_closure(results) -> dict:
    """closure 결과 목록 → 최종 verdict.

    - 4개 모두 clean PRODUCTION_READY(+records) → ALL_REMAINING_NON_EXCLUDED_SOURCES_READY
    - 일부라도 데이터/대기/검증된 blocker로 정직하게 처리됨(최소 1개 ready) →
      PARTIAL_WITH_VERIFIED_HARD_BLOCKERS
    - 아무것도 못 닫음 → BLOCKED
    """
    results = list(results)
    ready = [r for r in results if r.is_production_ready()]
    ready_with_data = [r for r in results if r.is_ready_with_data()]
    degraded = [r for r in results if r.is_degraded()]
    pending = [r for r in results if r.is_pending_resume()]
    blockers = [r for r in results if r.is_hard_blocker()]
    review = [r for r in results if r.final_status == NEEDS_OPERATOR_REVIEW]

    if results and len(ready) == len(results):
        verdict = "ALL_REMAINING_NON_EXCLUDED_SOURCES_READY"
    elif ready_with_data or pending or blockers:
        verdict = "PARTIAL_WITH_VERIFIED_HARD_BLOCKERS"
    else:
        verdict = "BLOCKED"

    return {
        "verdict": verdict,
        "production_ready": [r.source_id for r in ready],
        "degraded_preview_only": [r.source_id for r in degraded],
        "pending_resume": [r.source_id for r in pending],
        "verified_hard_blockers": [r.source_id for r in blockers],
        "needs_operator_review": [r.source_id for r in review],
        "degraded_remaining": len(degraded),
        "external_rate_limited_remaining": len(pending),
    }
