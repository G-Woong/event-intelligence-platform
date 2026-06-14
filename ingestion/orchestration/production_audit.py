"""Live artifact expansion 생산성 audit (Phase D-P / E-0, 설계 09/12).

실제 저장된 수집 artifact를 읽어 **article-level 분해가 실제로 일어나는지** 측정한다.
핵심 원칙: *artifact 존재 ≠ candidate 분해 성공*. 긍정편향을 만들지 않기 위해
``parse_artifact_text``의 실제 산출만 집계하고(seed source-level fallback을 끼워넣지 않음),
분해 실패는 ``production_risk``로 정직하게 표시한다.

numeric/market payload는 기사형과 분리 판정한다: 유효 JSON이면 기사 0개라도 본문 누락이
아니라 ``structured_signal``(numeric_exempt)로 본다. 단 rate-limit/오류 응답으로 보이는
payload는 ``possible_rate_limit_payload``로 별도 표시한다(성공처럼 위장하지 않는다).

stdlib + 기존 파서/판정기만 사용. 신규 설치 0.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from ingestion.orchestration.artifact_parser import parse_artifact_text
from ingestion.orchestration.body_state import assess_body_state

# 기사형으로 취급하는 purpose(본문/URL 기대). 이 외(numeric/trend)는 structured signal.
_ARTICLE_PURPOSES = frozenset({"news", "community", "search", "regulatory", "domain"})
_NUMERIC_PURPOSES = frozenset({"numeric", "trend"})
# JSON 최상위에 데이터 없이 이 키만 있으면 rate-limit/오류 응답으로 의심한다(값은 보지 않는다).
_RATE_LIMIT_MARKER_KEYS = frozenset({
    "Note", "Information", "Error Message", "error", "message", "status_message",
})
# 1차 분해 파서가 "분해 실패"임을 뜻하는 parser_name(0 candidate 동반).
_FAILURE_PARSERS = frozenset({
    "empty", "json_malformed", "xml_malformed", "json_unrecognized",
    "generic_json_list", "xml_no_items", "html_unsupported",
})

_EXTRACTION_STATES = (
    "present", "partial", "snippet_only", "numeric_exempt",
    "missing", "no_artifact", "parser_error", "malformed",
)


@dataclass(frozen=True)
class SourceExpansionAudit:
    source_id: str
    artifact_path: Optional[str]
    artifact_exists: bool
    parser_name: Optional[str]
    candidate_count: int
    fallback_used: bool
    parse_error_count: int
    title_present_count: int
    url_present_count: int
    canonical_url_count: int
    body_state_counts: dict[str, int]
    evidence_path_present: bool
    production_risk: Optional[str]
    # 보조 지표(보고 정밀도). 스펙 핵심 필드 외 확장.
    purpose: Optional[str] = None
    source_group: Optional[str] = None
    published_at_present_count: int = 0
    structured_signal_count: int = 0
    risk_flags: tuple[str, ...] = field(default_factory=tuple)


def _empty_state_counts() -> dict[str, int]:
    return {s: 0 for s in _EXTRACTION_STATES}


def _looks_like_rate_limit(text: str) -> bool:
    """JSON 최상위가 데이터 컨테이너 없이 marker 키만 가진 경우(우회/위장 방지)."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    has_marker = any(k in data for k in _RATE_LIMIT_MARKER_KEYS)
    has_container = any(
        isinstance(v, (list, dict)) and v for v in data.values()
    )
    return has_marker and not has_container


def audit_artifact_text(
    text: Optional[str],
    *,
    source_id: str,
    purpose: Optional[str] = None,
    source_group: Optional[str] = None,
    confirmation_policy: Optional[str] = None,
    artifact_path: Optional[str] = None,
    fmt: Optional[str] = None,
    full_threshold: Optional[int] = None,
) -> SourceExpansionAudit:
    """단일 artifact 텍스트의 분해 생산성을 감사한다(faithful: parser 실제 산출만)."""
    counts = _empty_state_counts()
    is_numeric = (purpose in _NUMERIC_PURPOSES) or (source_group == "market")
    risks: list[str] = []

    if text is None:
        return SourceExpansionAudit(
            source_id=source_id, artifact_path=artifact_path, artifact_exists=False,
            parser_name=None, candidate_count=0, fallback_used=False,
            parse_error_count=0, title_present_count=0, url_present_count=0,
            canonical_url_count=0, body_state_counts=counts,
            evidence_path_present=False, production_risk="artifact_missing",
            purpose=purpose, source_group=source_group, risk_flags=("artifact_missing",),
        )

    candidates, parser_name, errors = parse_artifact_text(
        text, source_id=source_id, confirmation_policy=confirmation_policy,
        raw_artifact_path=artifact_path, fmt=fmt,
    )

    title_present = url_present = canonical_present = published_present = 0
    for c in candidates:
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

    structured_signal = 0
    fallback_used = False
    # numeric/market: 기사 0개라도 유효 payload면 structured signal(본문 누락 아님).
    if not candidates and is_numeric:
        if parser_name in ("json_malformed", "xml_malformed"):
            risks.append("malformed_numeric_artifact")
            counts["malformed"] += 1
        elif _looks_like_rate_limit(text):
            risks.append("possible_rate_limit_payload")
            structured_signal = 1
            counts["numeric_exempt"] += 1
            fallback_used = True
        else:
            structured_signal = 1
            counts["numeric_exempt"] += 1
            fallback_used = True

    # ── production risk 판정(정직하게 실패를 드러낸다) ──
    if errors:
        risks.append("parse_errors_present")
    if parser_name == "html_unsupported":
        risks.append("html_not_decomposed")
    if not candidates and structured_signal == 0:
        risks.append("no_candidates_from_artifact")
    if candidates and not is_numeric:
        if title_present == 0:
            risks.append("all_titles_missing")
        if url_present == 0:
            risks.append("all_urls_missing")
        elif canonical_present == 0:
            risks.append("no_canonical_from_urls")
    # rate-limit 위장 탐지(기사형이라도 marker-only면 의심)
    if not is_numeric and not candidates and _looks_like_rate_limit(text):
        if "possible_rate_limit_payload" not in risks:
            risks.append("possible_rate_limit_payload")

    # 중복 제거, 순서 보존
    seen: set[str] = set()
    ordered = [r for r in risks if not (r in seen or seen.add(r))]

    return SourceExpansionAudit(
        source_id=source_id, artifact_path=artifact_path, artifact_exists=True,
        parser_name=parser_name, candidate_count=len(candidates),
        fallback_used=fallback_used, parse_error_count=len(errors),
        title_present_count=title_present, url_present_count=url_present,
        canonical_url_count=canonical_present, body_state_counts=counts,
        evidence_path_present=bool(artifact_path),
        production_risk=ordered[0] if ordered else None,
        purpose=purpose, source_group=source_group,
        published_at_present_count=published_present,
        structured_signal_count=structured_signal, risk_flags=tuple(ordered),
    )


def _fmt_from_path(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    return {".json": "json", ".xml": "xml", ".txt": "extracted_text"}.get(ext)


def audit_artifact_file(
    artifact_path: str | Path,
    *,
    source_id: str,
    purpose: Optional[str] = None,
    source_group: Optional[str] = None,
    confirmation_policy: Optional[str] = None,
    max_bytes: int = 8_000_000,
) -> SourceExpansionAudit:
    """디스크 artifact 파일을 읽어 감사한다. 없거나 읽기 실패면 artifact_missing."""
    path = Path(artifact_path)
    if not path.exists() or not path.is_file():
        return audit_artifact_text(
            None, source_id=source_id, purpose=purpose, source_group=source_group,
            confirmation_policy=confirmation_policy, artifact_path=str(path),
        )
    try:
        if path.stat().st_size > max_bytes:
            text = path.read_text(encoding="utf-8", errors="replace")[:max_bytes]
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return audit_artifact_text(
            None, source_id=source_id, purpose=purpose, source_group=source_group,
            confirmation_policy=confirmation_policy, artifact_path=str(path),
        )
    return audit_artifact_text(
        text, source_id=source_id, purpose=purpose, source_group=source_group,
        confirmation_policy=confirmation_policy, artifact_path=str(path),
        fmt=_fmt_from_path(path),
    )


def summarize_expansion(audits: Sequence[SourceExpansionAudit]) -> dict:
    """audit 목록 → 집계(보고용). 총계 + body 상태 분포 + group별 분포."""
    body_totals = _empty_state_counts()
    group_body: dict[str, dict[str, int]] = {}
    totals = {
        "sources": len(audits),
        "artifact_exists": 0,
        "candidate_total": 0,
        "structured_signal_total": 0,
        "fallback_sources": 0,
        "parse_error_sources": 0,
        "title_present": 0,
        "url_present": 0,
        "canonical_present": 0,
        "published_present": 0,
        "sources_with_risk": 0,
    }
    risk_tally: dict[str, int] = {}
    for a in audits:
        if a.artifact_exists:
            totals["artifact_exists"] += 1
        totals["candidate_total"] += a.candidate_count
        totals["structured_signal_total"] += a.structured_signal_count
        if a.fallback_used:
            totals["fallback_sources"] += 1
        if a.parse_error_count:
            totals["parse_error_sources"] += 1
        totals["title_present"] += a.title_present_count
        totals["url_present"] += a.url_present_count
        totals["canonical_present"] += a.canonical_url_count
        totals["published_present"] += a.published_at_present_count
        if a.risk_flags:
            totals["sources_with_risk"] += 1
        for flag in a.risk_flags:
            risk_tally[flag] = risk_tally.get(flag, 0) + 1
        for state, n in a.body_state_counts.items():
            body_totals[state] = body_totals.get(state, 0) + n
            grp = a.source_group or "unknown"
            group_body.setdefault(grp, _empty_state_counts())
            group_body[grp][state] = group_body[grp].get(state, 0) + n
    return {
        "totals": totals,
        "body_state_distribution": body_totals,
        "body_state_by_group": group_body,
        "risk_tally": risk_tally,
    }
