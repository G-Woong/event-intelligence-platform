"""Phase G-3 EvidenceGate — record의 evidence '형태(shape)'와 알려진 둔갑 패턴을 검사하는 게이트.

정직한 범위 한정(적대 리뷰 HIGH-2 흡수): 이 게이트는 **네트워크 0**이므로 URL의 live 여부나
관련성(relevance)을 검증하지 못한다. 그 1차 검증(실 url 존재/항목 스킵)은 **fetcher**가 수집
시점에 강제한다(fetch_culture_info/fetch_product_hunt: 실 url/시간 없으면 record 자체를 만들지
않음). 본 게이트는 그 위에 얹는 **shape 린터 + 알려진 dead/synthetic 패턴 regression 가드**다:
- 알려진 synthetic/dead 패턴 거부: producthunt 합성 slug(/posts/...), culture.go.kr detailView shell.
  (이 두 패턴은 G-3에서 실제로 고친 둔갑 — 재발 방지용 가드이며, 모든 dead url을 잡지는 못한다.)
- local file path를 외부 evidence로 둔갑 거부: file://, 절대경로(C:\\, /Users/, /home/), outputs/.
- shape 검사: 외부 url 형태 / stable id(canonical) / time anchor / body·signal 라벨 존재.

ready_allowed=True 조건: 위 형태 요건 충족 AND 알려진 둔갑 패턴 아님. 절대적 "진짜 evidence" 보증이
아니라 "형태가 맞고 알려진 가짜가 아님"의 보증이다 — 승격의 필요조건이지 충분조건이 아니다.

네트워크 0, stdlib만. 신규 설치 0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# synthetic/dead evidence 패턴(둔갑 거부)
_SYNTHETIC_URL_PATTERNS = (
    re.compile(r"producthunt\.com/posts/[a-z0-9-]+$", re.I),       # name 기반 합성 slug(실 url은 /products/...)
    re.compile(r"culture\.go\.kr/wantU/detail", re.I),             # 죽은 shell(909B) — 실 url은 detail2 api
)
_LOCAL_PATH_PATTERNS = (
    re.compile(r"^file://", re.I),
    re.compile(r"^[a-zA-Z]:[\\/]"),          # C:\ ...
    re.compile(r"^/(Users|home|var|tmp)/", re.I),
    re.compile(r"(^|/)outputs/", re.I),
)

EVIDENCE_HIGH = "high"
EVIDENCE_MEDIUM = "medium"
EVIDENCE_LOW = "low"


@dataclass(frozen=True)
class EvidenceGateResult:
    source_id: str
    record_type: str
    has_external_url: bool
    has_stable_id: bool
    has_time_anchor: bool
    has_body_or_signal_payload: bool
    body_state: Optional[str]
    evidence_confidence: str
    ready_allowed: bool
    downgrade_reason: Optional[str]


def _is_real_external_url(url: Optional[str]) -> bool:
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    if any(p.search(url) for p in _LOCAL_PATH_PATTERNS):
        return False
    if any(p.search(url) for p in _SYNTHETIC_URL_PATTERNS):
        return False
    return True


def _is_local_or_synthetic(url: Optional[str]) -> bool:
    if not isinstance(url, str):
        return False
    return (any(p.search(url) for p in _LOCAL_PATH_PATTERNS)
            or any(p.search(url) for p in _SYNTHETIC_URL_PATTERNS))


def evaluate_evidence(
    *,
    source_id: str,
    record: dict,
    require_body: bool = False,
) -> EvidenceGateResult:
    """EventQueue record 1건 → EvidenceGateResult.

    require_body=True면 body/signal이 단순 signal 라벨이 아닌 실 본문 상태여야 함(news/detail용).
    """
    rt = record.get("record_type") or "unknown"
    src_url = record.get("source_url_or_evidence")
    canonical = record.get("canonical_url")
    time_anchor = record.get("published_at_or_observed_at")
    body_state = record.get("body_state_or_signal")

    # local/synthetic을 외부 url로 둔갑하려는 시도는 즉시 차단
    synthetic = _is_local_or_synthetic(src_url) or _is_local_or_synthetic(canonical)
    has_url = _is_real_external_url(src_url) or _is_real_external_url(canonical)
    has_stable_id = bool(canonical) or bool(record.get("stable_id")) or has_url
    has_time = bool(time_anchor)
    has_payload = bool(body_state)
    if require_body:
        has_payload = bool(body_state) and body_state not in ("community_signal", "snippet_only", "")

    reasons = []
    if synthetic:
        reasons.append("SYNTHETIC_OR_LOCAL_EVIDENCE")
    if not has_url:
        reasons.append("NO_STABLE_EXTERNAL_URL")
    if not has_stable_id:
        reasons.append("NO_STABLE_ID")
    if not has_time:
        reasons.append("NO_TIME_ANCHOR")
    if not has_payload:
        reasons.append("NO_BODY_OR_SIGNAL_PAYLOAD")

    ready = not reasons
    confidence = EVIDENCE_HIGH if ready else (EVIDENCE_MEDIUM if (has_url and has_time) else EVIDENCE_LOW)
    return EvidenceGateResult(
        source_id=source_id, record_type=rt,
        has_external_url=has_url, has_stable_id=has_stable_id, has_time_anchor=has_time,
        has_body_or_signal_payload=has_payload, body_state=body_state,
        evidence_confidence=confidence, ready_allowed=ready,
        downgrade_reason=(";".join(reasons) if reasons else None),
    )


def gate_records(source_id: str, records, *, require_body: bool = False) -> dict:
    """record 목록 → 집계 게이트 결과. 모두 ready여야 ready_allowed=True.

    반환: {ready_allowed, ready_count, total, downgrade_reasons, per_record}
    """
    per = [evaluate_evidence(source_id=source_id, record=r, require_body=require_body) for r in records]
    ready_count = sum(1 for g in per if g.ready_allowed)
    reasons: list[str] = []
    for g in per:
        if g.downgrade_reason:
            reasons.extend(g.downgrade_reason.split(";"))
    return {
        "source_id": source_id,
        "total": len(per),
        "ready_count": ready_count,
        # source가 ready 자격을 가지려면 최소 1건 이상이 ready여야 한다(0건 → 자격 없음).
        "ready_allowed": ready_count > 0,
        "downgrade_reasons": tuple(sorted(set(reasons))),
        "per_record": tuple(per),
    }
