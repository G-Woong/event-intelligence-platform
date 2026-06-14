"""소스별 본문 추출 실측 audit (Phase E-1, 설계 04/05/09).

저장된 수집 artifact(또는 주입 텍스트)를 소스별로 분해해 **실제로 상용 서비스에 쓸 수 있는
본문/정보 데이터가 나오는지** 측정한다. 핵심 원칙(긍정편향 금지):
  - snippet을 full body로 포장하지 않는다(body_state cascade가 분리).
  - numeric/structured signal을 기사 본문 성공으로 섞지 않는다.
  - candidate_count 숫자만으로 성공을 판정하지 않는다(body_state/pre_gate로 쪼갠다).
  - 분해 0은 원인(에러 봉투/2-step/중첩/HTML/키 없음)을 risk_flag로 정직하게 남긴다.

이 모듈은 **기존 parser/body_state/pre_gate를 재사용**하며 새 본문 fetch를 하지 않는다
(네트워크 0). 시각은 호출자가 주입한다(결정성). stdlib만 사용. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.artifact_parser import parse_artifact_text
from ingestion.orchestration.audit_trace import TraceRecorder
from ingestion.orchestration.body_state import BodyExtractionState, assess_body_state
from ingestion.orchestration.quality_pre_gate import QualityPreGateResult, evaluate_pre_gate

_NUMERIC_PURPOSES = frozenset({"numeric", "trend"})
# 0분해의 원인 분류(parser_name → parser_gap_reason). 상용 readiness 판정 입력.
_PARSER_GAP_REASON = {
    "api_error_payload": "api_error_or_key_missing",
    "html_unsupported": "html_not_decomposed",
    "json_unrecognized": "schema_unknown",
    "json_malformed": "malformed_artifact",
    "xml_malformed": "malformed_artifact",
    "xml_no_items": "empty_feed",
    "generic_json_list": "list_without_dict_items",
    "empty": "empty_artifact",
}


@dataclass(frozen=True)
class CandidateInspection:
    """단일 candidate의 본문 상태 + 사전 게이트 판정(샘플 저장/보고 입력)."""
    index: int
    candidate: ArticleCandidate
    body_state: BodyExtractionState
    pre_gate: QualityPreGateResult


@dataclass(frozen=True)
class SourceBodyAudit:
    source_id: str
    source_group: Optional[str]
    purpose: Optional[str]
    artifact_path: Optional[str]
    artifact_exists: bool
    parser_name: Optional[str]
    candidate_count: int
    parse_error_count: int
    # body_state 분포(긍정편향 방지: present/snippet/numeric를 명확히 분리)
    body_present_count: int
    body_partial_count: int
    snippet_only_count: int
    body_missing_count: int
    numeric_exempt_count: int
    parser_error_count: int
    malformed_count: int
    structured_signal_count: int
    # 식별/링크 메타
    title_present_count: int
    url_present_count: int
    canonical_url_count: int
    published_at_count: int
    # pre_gate 분포
    pre_gate_pass: int
    pre_gate_hold: int
    pre_gate_reject: int
    parser_gap_reason: Optional[str]
    risk_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceBodyAuditResult:
    audit: SourceBodyAudit
    inspections: list[CandidateInspection] = field(default_factory=list)


def _is_numeric(purpose: Optional[str], source_group: Optional[str]) -> bool:
    return (purpose in _NUMERIC_PURPOSES) or (source_group == "market")


def audit_source_body(
    text: Optional[str],
    *,
    source_id: str,
    purpose: Optional[str] = None,
    source_group: Optional[str] = None,
    confirmation_policy: Optional[str] = None,
    artifact_path: Optional[str] = None,
    fmt: Optional[str] = None,
    full_threshold: Optional[int] = None,
    recorder: Optional[TraceRecorder] = None,
    timestamp: str = "",
    publication_policy: Optional[dict] = None,
) -> SourceBodyAuditResult:
    """artifact 텍스트 1건의 본문 추출/게이트 적합성을 소스별로 감사한다.

    예외를 던지지 않는다(실패 source가 전체 run을 죽이지 않도록). 분해 불가/에러는
    risk_flags + parser_gap_reason으로 보고한다. recorder가 있으면 stage trace를 남긴다.
    """
    def trace(stage: str, status: str, message: str = "", **metrics) -> None:
        if recorder is not None:
            recorder.record(source_id, stage, status, timestamp=timestamp,
                            message=message, metrics=metrics)

    is_numeric = _is_numeric(purpose, source_group)

    if text is None:
        trace("artifact_checked", "warn", "artifact_missing")
        audit = _empty_audit(
            source_id, source_group, purpose, artifact_path, artifact_exists=False,
            parser_name=None, parser_gap_reason="no_artifact",
            risk_flags=("no_artifact",),
        )
        trace("source_completed", "warn", "no_artifact", candidate_count=0)
        return SourceBodyAuditResult(audit=audit, inspections=[])

    trace("artifact_checked", "ok", "artifact_present", bytes=len(text))
    trace("candidate_expansion_started", "ok")
    try:
        candidates, parser_name, errors = parse_artifact_text(
            text, source_id=source_id, confirmation_policy=confirmation_policy,
            raw_artifact_path=artifact_path, fmt=fmt,
        )
    except Exception as exc:  # 파서 자체 예외도 source 단위로 격리
        trace("source_failed", "error", "parse_exception", error_type=type(exc).__name__)
        audit = _empty_audit(
            source_id, source_group, purpose, artifact_path, artifact_exists=True,
            parser_name="parser_exception", parser_gap_reason="parser_exception",
            parse_error_count=1, risk_flags=("parser_exception",),
        )
        return SourceBodyAuditResult(audit=audit, inspections=[])

    trace("candidate_expansion_finished", "ok", parser_name,
          candidate_count=len(candidates), parse_error_count=len(errors))

    inspections: list[CandidateInspection] = []
    counts = {
        "present": 0, "partial": 0, "snippet_only": 0, "missing": 0,
        "numeric_exempt": 0, "parser_error": 0, "malformed": 0, "no_artifact": 0,
    }
    title_present = url_present = canonical_present = published_present = 0
    pg = {"pass": 0, "hold": 0, "reject": 0}

    for i, c in enumerate(candidates):
        if c.title:
            title_present += 1
        if c.source_url:
            url_present += 1
        if c.canonical_url:
            canonical_present += 1
        if c.published_at:
            published_present += 1
        state = assess_body_state(
            body_text=c.body_text, summary=c.summary, purpose=purpose,
            numeric_payload_exempt=c.numeric_payload_exempt, parse_error=c.parse_error,
            full_threshold=full_threshold,
        )
        counts[state.extraction_status] = counts.get(state.extraction_status, 0) + 1
        result = evaluate_pre_gate(
            c, purpose=purpose, source_group=source_group,
            confirmation_policy=confirmation_policy,
            publication_policy=publication_policy, full_threshold=full_threshold,
        )
        pg[result.decision] = pg.get(result.decision, 0) + 1
        inspections.append(CandidateInspection(index=i, candidate=c, body_state=state,
                                                pre_gate=result))

    trace("body_state_assessed", "ok", present=counts["present"],
          snippet_only=counts["snippet_only"], numeric_exempt=counts["numeric_exempt"],
          missing=counts["missing"])
    trace("canonicalized", "ok", canonical_url_count=canonical_present,
          network_calls=0)
    trace("quality_pre_gate_applied", "ok", **pg)

    # ── structured_signal & risk 판정(정직하게) ──
    structured_signal = counts["numeric_exempt"]
    risks: list[str] = []
    if errors:
        risks.append("parse_errors_present")
    if parser_name == "html_unsupported":
        risks.append("html_not_decomposed")
    if not candidates:
        # numeric/market 0분해는 structured signal로 환원하지 않는다(여기선 분해가 목표).
        risks.append("no_candidates_from_artifact")
    else:
        if not is_numeric and title_present == 0:
            risks.append("all_titles_missing")
        if not is_numeric and url_present == 0:
            risks.append("all_urls_missing")
        elif not is_numeric and url_present and canonical_present == 0:
            risks.append("no_canonical_from_urls")
        if not is_numeric and counts["present"] == 0 and counts["partial"] == 0:
            # 기사형인데 본문이 하나도 안 나옴(snippet/missing만) — 본문 추출 갭
            risks.append("no_full_body_extracted")

    parser_gap = None
    if not candidates:
        parser_gap = _PARSER_GAP_REASON.get(parser_name or "", "no_candidates")

    seen: set[str] = set()
    ordered = tuple(r for r in risks if not (r in seen or seen.add(r)))

    audit = SourceBodyAudit(
        source_id=source_id, source_group=source_group, purpose=purpose,
        artifact_path=artifact_path, artifact_exists=True, parser_name=parser_name,
        candidate_count=len(candidates), parse_error_count=len(errors),
        body_present_count=counts["present"], body_partial_count=counts["partial"],
        snippet_only_count=counts["snippet_only"], body_missing_count=counts["missing"],
        numeric_exempt_count=counts["numeric_exempt"],
        parser_error_count=counts["parser_error"], malformed_count=counts["malformed"],
        structured_signal_count=structured_signal,
        title_present_count=title_present, url_present_count=url_present,
        canonical_url_count=canonical_present, published_at_count=published_present,
        pre_gate_pass=pg["pass"], pre_gate_hold=pg["hold"], pre_gate_reject=pg["reject"],
        parser_gap_reason=parser_gap, risk_flags=ordered,
    )
    trace("source_completed", "ok", parser_name or "",
          candidate_count=len(candidates), body_present=counts["present"])
    return SourceBodyAuditResult(audit=audit, inspections=inspections)


def _empty_audit(source_id, source_group, purpose, artifact_path, *, artifact_exists,
                 parser_name, parser_gap_reason, parse_error_count=0,
                 risk_flags=()):
    return SourceBodyAudit(
        source_id=source_id, source_group=source_group, purpose=purpose,
        artifact_path=artifact_path, artifact_exists=artifact_exists,
        parser_name=parser_name, candidate_count=0, parse_error_count=parse_error_count,
        body_present_count=0, body_partial_count=0, snippet_only_count=0,
        body_missing_count=0, numeric_exempt_count=0, parser_error_count=0,
        malformed_count=0, structured_signal_count=0, title_present_count=0,
        url_present_count=0, canonical_url_count=0, published_at_count=0,
        pre_gate_pass=0, pre_gate_hold=0, pre_gate_reject=0,
        parser_gap_reason=parser_gap_reason, risk_flags=tuple(risk_flags),
    )


def summarize_body_audits(audits: Sequence[SourceBodyAudit]) -> dict:
    """소스별 audit → 총계(보고용). group별 body 분포 포함. 숫자를 쪼개서 정직하게."""
    totals = {
        "sources": len(audits), "artifact_exists": 0, "candidate_total": 0,
        "body_present": 0, "body_partial": 0, "snippet_only": 0, "body_missing": 0,
        "numeric_exempt": 0, "structured_signal": 0,
        "title_present": 0, "url_present": 0, "canonical_url": 0,
        "pre_gate_pass": 0, "pre_gate_hold": 0, "pre_gate_reject": 0,
        "zero_decompose_sources": 0,
    }
    by_group: dict[str, dict[str, int]] = {}
    parser_gap_tally: dict[str, int] = {}
    for a in audits:
        if a.artifact_exists:
            totals["artifact_exists"] += 1
        totals["candidate_total"] += a.candidate_count
        totals["body_present"] += a.body_present_count
        totals["body_partial"] += a.body_partial_count
        totals["snippet_only"] += a.snippet_only_count
        totals["body_missing"] += a.body_missing_count
        totals["numeric_exempt"] += a.numeric_exempt_count
        totals["structured_signal"] += a.structured_signal_count
        totals["title_present"] += a.title_present_count
        totals["url_present"] += a.url_present_count
        totals["canonical_url"] += a.canonical_url_count
        totals["pre_gate_pass"] += a.pre_gate_pass
        totals["pre_gate_hold"] += a.pre_gate_hold
        totals["pre_gate_reject"] += a.pre_gate_reject
        if a.candidate_count == 0:
            totals["zero_decompose_sources"] += 1
        if a.parser_gap_reason:
            parser_gap_tally[a.parser_gap_reason] = parser_gap_tally.get(a.parser_gap_reason, 0) + 1
        grp = a.source_group or "unknown"
        g = by_group.setdefault(grp, {"present": 0, "partial": 0, "snippet_only": 0,
                                      "missing": 0, "numeric_exempt": 0})
        g["present"] += a.body_present_count
        g["partial"] += a.body_partial_count
        g["snippet_only"] += a.snippet_only_count
        g["missing"] += a.body_missing_count
        g["numeric_exempt"] += a.numeric_exempt_count
    return {
        "totals": totals,
        "body_state_by_group": by_group,
        "parser_gap_tally": parser_gap_tally,
    }
