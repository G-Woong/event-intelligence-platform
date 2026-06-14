"""소스별 production readiness 보고 (Phase E-1, 설계 09/12).

``SourceBodyAudit`` + ``SourceProfile``을 결합해 **소스별로 상용 서비스에 즉시 쓸 수 있는지**
등급을 매긴다. 등급은 긍정편향 없이 본문/구조신호/파서갭/키부재/차단을 구분한다.

production_readiness:
  PRODUCTION_READY_SIGNAL  — 본문 또는 즉시 사용 가능한 구조 신호 확보
  STRUCTURED_SIGNAL_ONLY   — numeric/trend 등 구조 신호 전용(본문 불요)
  NEEDS_BODY_FETCH         — 기사 후보는 나오나 본문이 snippet/누락(전체 기사 fetch 필요)
  NEEDS_PARSER             — 스키마 미해독/2-step 등 파서 보강 필요
  HTML_UNSUPPORTED         — HTML 페이지 본문 분해 미지원
  KEY_MISSING              — API 키 부재로 에러/미수집
  RATE_LIMITED             — rate-limit 응답
  BLOCKED_NO_BYPASS        — robots/login/paywall 차단(우회 금지)
  INSUFFICIENT_DATA        — 그 외 데이터 부족

stdlib만 사용. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from ingestion.orchestration.source_body_audit import SourceBodyAudit

_BLOCKED_SKIP_REASONS = frozenset({
    "robots_or_policy_block", "login_wall_no_bypass", "paywall_no_bypass",
    "blocked_policy_no_bypass",
})


@dataclass(frozen=True)
class SourceBodyReport:
    source_id: str
    source_group: Optional[str]
    purpose: Optional[str]
    enabled: bool
    live_eligible: str
    requires_api_key: bool
    api_key_ready: Optional[bool]
    probe_status: str
    artifact_exists: bool
    artifact_type: Optional[str]
    candidate_count: int
    body_present_count: int
    body_partial_count: int
    snippet_only_count: int
    body_missing_count: int
    numeric_exempt_count: int
    structured_signal_count: int
    canonical_url_count: int
    pre_gate_pass: int
    pre_gate_hold: int
    pre_gate_reject: int
    sample_saved_count: int
    parser_gap_reason: Optional[str]
    body_gap_reason: Optional[str]
    production_readiness: str
    next_action: str
    risk_flags: tuple[str, ...] = field(default_factory=tuple)


def _body_gap_reason(audit: SourceBodyAudit) -> Optional[str]:
    if audit.candidate_count == 0:
        return None  # 분해 자체가 안 됨 → parser_gap_reason이 담당
    if audit.numeric_exempt_count == audit.candidate_count:
        return None  # 전부 구조 신호 → 본문 갭 아님
    if audit.body_present_count > 0:
        return None
    if audit.snippet_only_count > 0:
        return "snippet_only_needs_full_fetch"
    if audit.body_missing_count > 0:
        return "body_missing_metadata_only"
    return None


def classify_production_readiness(
    audit: SourceBodyAudit,
    *,
    requires_api_key: bool = False,
    api_key_ready: Optional[bool] = None,
    skip_reason: Optional[str] = None,
) -> tuple[str, str]:
    """(production_readiness, next_action)을 결정한다. 긍정편향 없이 실패를 분류."""
    # 1) 정책 차단(우회 금지)
    if skip_reason in _BLOCKED_SKIP_REASONS:
        return "BLOCKED_NO_BYPASS", "정책 차단 — 우회 없음. 대체 소스/공식 API 검토(separate round)."

    # 2) artifact 자체가 없음
    if not audit.artifact_exists:
        if requires_api_key and not api_key_ready:
            return "KEY_MISSING", "API 키 설정 후 재수집 필요(.env)."
        return "INSUFFICIENT_DATA", "아직 수집 artifact 없음 — 1회 수집 후 재감사."

    parser = audit.parser_name or ""

    # 3) 에러/상태 봉투
    if parser == "api_error_payload":
        if requires_api_key and not api_key_ready:
            return "KEY_MISSING", "에러 응답(키/파라미터 부재) — 키 설정 후 재수집."
        return "NEEDS_PARSER", "에러/상태 봉투 — 요청 파라미터/엔드포인트 점검."

    # 4) rate-limit 의심
    if "possible_rate_limit_payload" in audit.risk_flags:
        return "RATE_LIMITED", "rate-limit 응답 — 간격 확대 후 재수집(우회 금지)."

    # 5) HTML 미지원
    if parser == "html_unsupported":
        return "HTML_UNSUPPORTED", "HTML 본문 분해 미지원 — 소스별 selector/fetch(Phase E)."

    # 6) 분해 0(스키마/2-step)
    if audit.candidate_count == 0:
        return "NEEDS_PARSER", f"0분해({audit.parser_gap_reason}) — 소스별 파서/2-step 보강."

    # 7) 분해는 되나 식별 필드(title/url) 미매핑 — source-specific 파서 필요
    if "all_titles_missing" in audit.risk_flags:
        return "NEEDS_PARSER", "분해되나 title/url 미매핑 — source-specific 필드 매핑(Phase E)."

    # 8) numeric/구조 신호 전용
    if audit.numeric_exempt_count == audit.candidate_count:
        return "STRUCTURED_SIGNAL_ONLY", "구조 신호(시세/트렌드) — 본문 불요, 즉시 신호 활용."

    # 8) 본문 확보
    if audit.body_present_count > 0:
        return "PRODUCTION_READY_SIGNAL", "본문 확보 — event feed 전 단계 적합."

    # 9) 기사 후보는 있으나 본문 없음
    if audit.snippet_only_count > 0 or audit.body_missing_count > 0:
        return "NEEDS_BODY_FETCH", "후보는 분해되나 본문 snippet/누락 — 전체 기사 fetch(Phase E)."

    return "INSUFFICIENT_DATA", "데이터 부족 — 원인 재확인."


def build_source_report(
    audit: SourceBodyAudit,
    *,
    enabled: bool = True,
    live_eligible: str = "false",
    requires_api_key: bool = False,
    api_key_ready: Optional[bool] = None,
    skip_reason: Optional[str] = None,
    probe_status: str = "reused_artifact",
    artifact_type: Optional[str] = None,
    sample_saved_count: int = 0,
) -> SourceBodyReport:
    readiness, next_action = classify_production_readiness(
        audit, requires_api_key=requires_api_key, api_key_ready=api_key_ready,
        skip_reason=skip_reason,
    )
    return SourceBodyReport(
        source_id=audit.source_id, source_group=audit.source_group,
        purpose=audit.purpose, enabled=enabled, live_eligible=live_eligible,
        requires_api_key=requires_api_key, api_key_ready=api_key_ready,
        probe_status=probe_status, artifact_exists=audit.artifact_exists,
        artifact_type=artifact_type, candidate_count=audit.candidate_count,
        body_present_count=audit.body_present_count,
        body_partial_count=audit.body_partial_count,
        snippet_only_count=audit.snippet_only_count,
        body_missing_count=audit.body_missing_count,
        numeric_exempt_count=audit.numeric_exempt_count,
        structured_signal_count=audit.structured_signal_count,
        canonical_url_count=audit.canonical_url_count,
        pre_gate_pass=audit.pre_gate_pass, pre_gate_hold=audit.pre_gate_hold,
        pre_gate_reject=audit.pre_gate_reject, sample_saved_count=sample_saved_count,
        parser_gap_reason=audit.parser_gap_reason, body_gap_reason=_body_gap_reason(audit),
        production_readiness=readiness, next_action=next_action,
        risk_flags=audit.risk_flags,
    )


def summarize_reports(reports: Sequence[SourceBodyReport]) -> dict:
    """소스별 보고 → readiness 분포 + group별 집계(보고용)."""
    readiness_dist: dict[str, int] = {}
    by_group: dict[str, dict[str, int]] = {}
    for r in reports:
        readiness_dist[r.production_readiness] = readiness_dist.get(r.production_readiness, 0) + 1
        grp = r.source_group or "unknown"
        g = by_group.setdefault(grp, {})
        g[r.production_readiness] = g.get(r.production_readiness, 0) + 1
    return {
        "sources": len(reports),
        "readiness_distribution": dict(sorted(readiness_dist.items(), key=lambda x: -x[1])),
        "readiness_by_group": by_group,
    }
