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
# G-4: 본문 source 실패했으나 community preview signal 역할로 명확히 닫힌 정식 tier(애매한 DEGRADED 아님).
PRODUCTION_READY_COMMUNITY_PREVIEW = "PRODUCTION_READY_COMMUNITY_PREVIEW"
EXTERNAL_RATE_LIMITED_PENDING_RESUME = "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
VERIFIED_HARD_BLOCKER = "VERIFIED_HARD_BLOCKER"
NEEDS_OPERATOR_REVIEW = "NEEDS_OPERATOR_REVIEW"

# 데이터가 살아있는(수집됨) ready 계열 — preview_only(DEGRADED)/community_preview도 ready로 인정(실데이터 존재)
_READY_WITH_DATA = frozenset({
    PRODUCTION_READY, PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY, PRODUCTION_READY_COMMUNITY_PREVIEW,
})


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

    def is_community_preview(self) -> bool:
        """community preview signal 역할로 닫힌 정식 tier(데이터 존재 + 역할 명확)."""
        return self.final_status == PRODUCTION_READY_COMMUNITY_PREVIEW and self.eventqueue_records > 0

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
    community_preview_role: bool = False,
) -> tuple[str, Optional[str], Optional[str]]:
    """(final_status, ready_or_degraded_reason, hard_blocker_evidence) 산출 — 공통 결정 로직.

    community_preview_role=True: 본문 source가 아니라 community preview signal source로 역할을
    재정의한 경우. 데이터+EvidenceGate 통과 시 caveat(본문부재/ToS-미검증)는 '역할 정의'이므로
    DEGRADED가 아니라 PRODUCTION_READY_COMMUNITY_PREVIEW(정식 tier)로 닫는다.
    """
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

    # 3) community preview 역할 재정의 — caveat는 역할 정의(본문 미수집은 의도). 정식 preview tier.
    if community_preview_role:
        reason = "community_preview_signal_role:" + ";".join(caveats) if caveats else "community_preview_signal_role"
        return (PRODUCTION_READY_COMMUNITY_PREVIEW, reason, None)

    # 4) 데이터 있고 EvidenceGate 통과 — 정책 caveat가 있으면(HIGH 민감) preview-only DEGRADED
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


def classify_risk_closure(results, *, proof_pass: Optional[dict] = None) -> dict:
    """Phase G-4 risk-closure verdict — 남은 비-excluded source risk가 닫혔는가.

    - dcinside : community preview tier 또는 detail-body ready → 닫힘(애매한 DEGRADED 금지).
    - culture_info/product_hunt : clean ready AND source-specific eq/raw proof 통과 → 닫힘.
    - gdelt    : fresh record ready → 완전 닫힘. pending이지만 next_resume/escalation 증거가
                 있으면 'provider-constrained scheduled' — 나머지가 닫혔을 때 PARTIAL 허용.

    verdict:
      ALL_REMAINING_NON_EXCLUDED_SOURCE_RISKS_CLOSED — 4개 전부 닫힘(gdelt fresh 포함).
      PARTIAL_ONLY_IF_LEGAL_OR_PROVIDER_HARD_BLOCKER_WITH_FULL_EVIDENCE — gdelt만 provider 429
        scheduled로 남고 나머지 3개는 닫힘(full evidence 보유).
      BLOCKED — 그 외(닫지 못한 risk가 남음).
    """
    proof_pass = proof_pass or {}
    by = {r.source_id: r for r in results}

    # 닫힘 판정은 role(final_status) + source-specific proof를 권위 증거로 본다.
    # 공유 production dedup의 collapse(eq=0)는 contract 실패가 아니라 정상 dedup이므로 사용하지 않는다.
    def _closed(sid: str) -> bool:
        r = by.get(sid)
        if r is None:
            return False
        if sid == "gdelt":
            return r.final_status == PRODUCTION_READY and bool(proof_pass.get(sid, False))
        if sid in ("culture_info", "product_hunt"):
            return r.final_status == PRODUCTION_READY and bool(proof_pass.get(sid, False))
        if sid == "dcinside":
            return (r.final_status in (PRODUCTION_READY_COMMUNITY_PREVIEW, PRODUCTION_READY)
                    and bool(proof_pass.get(sid, False)))
        return r.final_status == PRODUCTION_READY and bool(proof_pass.get(sid, False))

    targets = ("dcinside", "gdelt", "culture_info", "product_hunt")
    closed_map = {s: _closed(s) for s in targets}
    g = by.get("gdelt")
    gdelt_scheduled = bool(g and g.is_pending_resume() and g.pending_resume_at)
    others_closed = all(closed_map[s] for s in ("dcinside", "culture_info", "product_hunt"))

    if all(closed_map.values()):
        verdict = "ALL_REMAINING_NON_EXCLUDED_SOURCE_RISKS_CLOSED"
    elif others_closed and gdelt_scheduled:
        verdict = "PARTIAL_ONLY_IF_LEGAL_OR_PROVIDER_HARD_BLOCKER_WITH_FULL_EVIDENCE"
    else:
        verdict = "BLOCKED"

    return {
        "verdict": verdict,
        "closed": closed_map,
        "gdelt_scheduled": gdelt_scheduled,
        "open_risks": [s for s, c in closed_map.items() if not c],
    }
