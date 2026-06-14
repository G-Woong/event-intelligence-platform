"""BodyExtractionState & cascade 판정 (Phase D-3, 설계 04 §1·§3).

ArticleCandidate의 본문 상태를 정규화한다. 핵심 원칙(04): **body_missing ≠ 실패**.
numeric/API payload는 본문 길이 게이트에서 면제하고, snippet을 full body로 과대평가하지 않는다.
이 상태는 Phase E 품질 게이트의 입력이 된다(여기서는 게이트 판정을 내리지 않는다).

extraction_status: present|missing|snippet_only|numeric_exempt|partial|malformed
                   |no_artifact|parser_error
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ingestion.orchestration.article_candidate import ArticleCandidate

# 본문 길이 임계(04 §13: 뉴스 200자, 커뮤니티 50자). full=완전 본문, partial=불완전 본문.
FULL_BODY_MIN = 200
COMMUNITY_FULL_MIN = 50
PARTIAL_MIN = 50  # 이 미만이면 본문으로 보지 않는다(snippet/누락으로 강등)

_NUMERIC_PURPOSES = frozenset({"numeric", "trend"})


@dataclass(frozen=True)
class BodyExtractionState:
    body_missing: bool
    body_source: Optional[str]   # body|summary|None
    body_length: int
    extraction_status: str
    numeric_payload_exempt: bool
    snippet_only: bool
    partial: bool
    reason: Optional[str] = None


def _full_threshold(purpose: Optional[str]) -> int:
    if purpose == "community":
        return COMMUNITY_FULL_MIN
    return FULL_BODY_MIN


def assess_body_state(
    *,
    body_text: Optional[str] = None,
    summary: Optional[str] = None,
    purpose: Optional[str] = None,
    numeric_payload_exempt: bool = False,
    parse_error: Optional[str] = None,
    artifact_present: bool = True,
    malformed: bool = False,
    full_threshold: Optional[int] = None,
) -> BodyExtractionState:
    """본문 상태를 cascade로 판정한다(설계 04 §3 우선순위).

    1) parser_error / malformed → 본문 판정 불가.
    2) artifact 없음 → no_artifact.
    3) numeric/API 면제 → numeric_exempt(본문 불요, body_missing=False).
    4) body_text ≥ 임계 → present.
    5) PARTIAL_MIN ≤ body_text < 임계 → partial(불완전 본문).
    6) body 부족 + summary 존재 → snippet_only(요약만; full body 아님).
    7) 그 외 → missing.
    """
    if parse_error:
        return BodyExtractionState(
            body_missing=True, body_source=None, body_length=0,
            extraction_status="parser_error", numeric_payload_exempt=False,
            snippet_only=False, partial=False, reason=parse_error,
        )
    if malformed:
        return BodyExtractionState(
            body_missing=True, body_source=None, body_length=0,
            extraction_status="malformed", numeric_payload_exempt=False,
            snippet_only=False, partial=False, reason="malformed_artifact",
        )
    if not artifact_present:
        return BodyExtractionState(
            body_missing=True, body_source=None, body_length=0,
            extraction_status="no_artifact", numeric_payload_exempt=False,
            snippet_only=False, partial=False, reason="no_artifact",
        )
    if numeric_payload_exempt or purpose in _NUMERIC_PURPOSES:
        # 시세/트렌드 신호: body 자체가 없는 게 정상(signal_only). 누락이 아니다.
        return BodyExtractionState(
            body_missing=False, body_source=None, body_length=0,
            extraction_status="numeric_exempt", numeric_payload_exempt=True,
            snippet_only=False, partial=False, reason="numeric_or_trend_signal",
        )

    body = (body_text or "").strip()
    summ = (summary or "").strip()
    threshold = full_threshold if full_threshold is not None else _full_threshold(purpose)
    blen = len(body)

    if blen >= threshold:
        return BodyExtractionState(
            body_missing=False, body_source="body", body_length=blen,
            extraction_status="present", numeric_payload_exempt=False,
            snippet_only=False, partial=False,
        )
    if blen >= PARTIAL_MIN:
        return BodyExtractionState(
            body_missing=False, body_source="body", body_length=blen,
            extraction_status="partial", numeric_payload_exempt=False,
            snippet_only=False, partial=True, reason=f"below_full_threshold:{threshold}",
        )
    if summ:
        # 본문은 없고 요약만 — full body로 취급하지 않는다(body_missing=True).
        return BodyExtractionState(
            body_missing=True, body_source="summary", body_length=len(summ),
            extraction_status="snippet_only", numeric_payload_exempt=False,
            snippet_only=True, partial=False, reason="summary_only_no_body",
        )
    return BodyExtractionState(
        body_missing=True, body_source=None, body_length=blen,
        extraction_status="missing", numeric_payload_exempt=False,
        snippet_only=False, partial=False, reason="no_body_no_summary",
    )


def assess_candidate_body(
    candidate: ArticleCandidate, *, purpose: Optional[str] = None,
) -> BodyExtractionState:
    """ArticleCandidate에서 본문 상태를 판정(파서 결과를 그대로 사용)."""
    return assess_body_state(
        body_text=candidate.body_text, summary=candidate.summary, purpose=purpose,
        numeric_payload_exempt=candidate.numeric_payload_exempt,
        parse_error=candidate.parse_error,
    )
