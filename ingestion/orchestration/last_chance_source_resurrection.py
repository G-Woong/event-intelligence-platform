"""Phase G2-1/G2-7 LastChanceSourceResurrection — 3개 source의 마지막 복구 결과 모델.

dcinside / google_trends_explore / gdelt를 조기 포기하지 않고, 정책 준수 범위에서
복구를 시도한 결과를 한 source당 하나의 LastChanceSourceResurrection으로 모은다.
final_status는 다음 중 하나로 정직하게 닫는다(추측 disable 금지):

  PRODUCTION_READY                              (live records + EventQueue/raw_events)
  PRODUCTION_READY_WITH_COOLDOWN                (records 있고 rate-limit cooldown 관리)
  EXTERNAL_RATE_LIMITED_PENDING_RESUME          (지금 throttle, 다음 run 자동 재개)
  POLICY_BLOCKED_NO_BYPASS_WITH_PROOF           (robots/정책 차단 + 증거)
  REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT         (compliant 경로 없음 + 증거)
  SOURCE_CHANGED_NEEDS_OPERATOR_REVIEW_WITH_EVIDENCE

stdlib만. 신규 설치 0. 네트워크 0(순수 조립/분류).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

PRODUCTION_READY = "PRODUCTION_READY"
PRODUCTION_READY_WITH_COOLDOWN = "PRODUCTION_READY_WITH_COOLDOWN"
# 공개 list/preview만 수집(본문 없음) + 정책 caveat(예: dcinside AI-차단 robots/ToS 미검증) →
# 데이터는 alive지만 degraded로 정직히 표기(적대 리뷰 흡수).
PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY = "PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY"
PENDING_RESUME = "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
POLICY_BLOCKED = "POLICY_BLOCKED_NO_BYPASS_WITH_PROOF"
REQUIRES_CONTRACT = "REQUIRES_OFFICIAL_API_KEY_OR_CONTRACT"
NEEDS_OPERATOR_REVIEW = "SOURCE_CHANGED_NEEDS_OPERATOR_REVIEW_WITH_EVIDENCE"

# production_ready로 인정되는 final_status(EventQueue/raw_events records > 0 필요는 호출자가 보장).
# PUBLIC_PREVIEW_ONLY는 실데이터를 수집하므로 ready로 인정하되, production_state에서는 DEGRADED.
_READY_STATUSES = frozenset({
    PRODUCTION_READY, PRODUCTION_READY_WITH_COOLDOWN, PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY,
})
# 정직한 pending(재개 가능) — terminal 아님
_PENDING_STATUSES = frozenset({PENDING_RESUME})
# 증거 있는 hard blocker
_BLOCKER_STATUSES = frozenset({POLICY_BLOCKED, REQUIRES_CONTRACT, NEEDS_OPERATOR_REVIEW})


@dataclass(frozen=True)
class LastChanceSourceResurrection:
    source_id: str
    previous_status: str
    previous_reason: str
    historical_success_evidence: Optional[str]
    policy_probe: Optional[Any]                 # SourcePolicyProbeResult (선택)
    strategy_ladder: tuple[str, ...]
    live_attempts: tuple[str, ...]
    successful_strategy: Optional[str]
    eventqueue_records: int
    raw_events_records: int
    final_status: str
    next_resume_at: Optional[str]
    hard_blocker_evidence: Optional[str]

    def is_production_ready(self) -> bool:
        return self.final_status in _READY_STATUSES and self.eventqueue_records > 0

    def is_pending_resume(self) -> bool:
        return self.final_status in _PENDING_STATUSES

    def is_hard_blocker(self) -> bool:
        return self.final_status in _BLOCKER_STATUSES

    def to_dict(self) -> dict:
        d = asdict(self)
        # policy_probe는 dataclass면 asdict로 직렬화됨; 아니면 문자열화
        pp = self.policy_probe
        if pp is not None and not isinstance(d.get("policy_probe"), dict):
            d["policy_probe"] = str(pp)
        return d


def classify_resurrection(results: list[LastChanceSourceResurrection]) -> dict:
    """3개 결과 → 전체 verdict 산출. ALL_READY는 모두 production_ready일 때만."""
    ready = [r for r in results if r.is_production_ready()]
    pending = [r for r in results if r.is_pending_resume()]
    blockers = [r for r in results if r.is_hard_blocker()]
    if results and len(ready) == len(results):
        verdict = "ALL_THREE_SOURCES_PRODUCTION_READY"
    elif blockers:
        verdict = "PARTIAL_WITH_HARD_BLOCKERS" if not pending else "PARTIAL_MIXED_PENDING_AND_BLOCKERS"
    elif pending:
        verdict = "PARTIAL_WITH_POLICY_COMPLIANT_PENDING_RESUME"
    else:
        verdict = "BLOCKED"
    return {
        "verdict": verdict,
        "production_ready": [r.source_id for r in ready],
        "pending_resume": [r.source_id for r in pending],
        "hard_blockers": [r.source_id for r in blockers],
        "total_eventqueue_records": sum(r.eventqueue_records for r in results),
        "total_raw_events_records": sum(r.raw_events_records for r in results),
    }
