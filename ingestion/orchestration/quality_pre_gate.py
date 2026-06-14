"""Phase E-0 품질 사전 게이트 (설계 09 §품질/안전 게이트).

ArticleCandidate가 상용화 품질로 넘어갈 수 있는 **최소 pre-gate**다. Phase E 전체
dedup 엔진이 아니라, candidate별 ``pass/hold/reject`` 판정 + dedup 키/발행시각 정규화/
boilerplate 추정/게시 정책을 산출한다. 원칙(09): 근거(evidence) 없는 후보는 게시 불가,
본문 누락은 실패가 아니라 hold, numeric/structured signal은 본문 게이트 면제,
원문 전문 게시 금지(preview_only).

stdlib만 사용(hashlib/datetime/email.utils/re/yaml). 신규 설치 0.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.body_state import assess_body_state

_PUBLICATION_POLICY_PATH = (
    Path(__file__).parent.parent / "configs" / "publication_policy.yaml"
)

# boilerplate 의심 마커(휴리스틱; 정밀 분류는 Phase E). 한/영 혼용.
_BOILERPLATE_MARKERS = (
    "subscribe", "sign up", "cookie", "all rights reserved", "terms of service",
    "privacy policy", "advertisement", "구독", "저작권", "무단 전재", "재배포 금지",
    "광고", "로그인", "쿠키",
)
_GDELT_SEENDATE = re.compile(r"^(\d{8})T?(\d{6})Z?$")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class QualityPreGateResult:
    source_id: str
    candidate_id: Optional[str]
    decision: str  # pass | hold | reject
    reasons: tuple[str, ...]
    normalized_published_at: Optional[str]
    canonical_url: Optional[str]
    evidence_ref: Optional[str]
    duplicate_key: Optional[str]
    boilerplate_risk: str          # low | medium | high | not_applicable
    publication_policy: str        # preview_only:<n> | no_public_preview


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def normalize_published_at(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """발행시각 → (ISO-8601 UTC, error). 파싱 불가 시 (None, 사유). 없으면 (None, None).

    지원: ISO-8601, RFC822(RSS pubDate), GDELT seendate(YYYYMMDDhhmmss), 날짜만(YYYY-MM-DD).
    인식 실패는 None + 사유로 정직하게 보고한다(없는 포맷을 지어내지 않는다).

    한계(정직 고지): (1) 날짜만(YYYY-MM-DD)은 시:분:초를 ``00:00:00 UTC``로 가정한다 —
    precision_lost가 발생할 수 있다. (2) 타임존 미표기 값은 UTC로 간주한다. Unix epoch,
    ``YYYY/MM/DD``, ``YYYY.MM.DD``, 한글 날짜 등은 미지원 → unrecognized(hold). 정밀 정규화는
    Phase E(소스별 published_at 매핑)에서 보강한다.
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, "empty"

    # ISO-8601 (Z 허용)
    try:
        return _to_utc_iso(datetime.fromisoformat(s.replace("Z", "+00:00"))), None
    except ValueError:
        pass
    # RFC822 (RSS pubDate)
    try:
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return _to_utc_iso(dt), None
    except (TypeError, ValueError):
        pass
    # GDELT seendate
    m = _GDELT_SEENDATE.match(s)
    if m:
        try:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            return _to_utc_iso(dt.replace(tzinfo=timezone.utc)), None
        except ValueError:
            pass
    # 날짜만
    if _DATE_ONLY.match(s):
        try:
            dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return _to_utc_iso(dt), None
        except ValueError:
            pass
    return None, "unrecognized_format"


def compute_duplicate_key(candidate: ArticleCandidate) -> Optional[str]:
    """canonical_url 우선, 없으면 source_id|title|published_at 해시. 모두 없으면 None."""
    if candidate.canonical_url:
        h = hashlib.sha1(candidate.canonical_url.encode("utf-8")).hexdigest()
        return f"url:{h[:16]}"
    title = candidate.title or ""
    published = candidate.published_at or ""
    if not title and not published:
        return None  # 식별 근거 없음 — dedup 키를 지어내지 않는다
    basis = f"{candidate.source_id}|{title}|{published}"
    h = hashlib.sha1(basis.encode("utf-8")).hexdigest()
    return f"meta:{h[:16]}"


def assess_boilerplate(candidate: ArticleCandidate) -> str:
    """본문/요약의 boilerplate 위험(휴리스틱). 텍스트 없으면 not_applicable."""
    text = (candidate.body_text or candidate.summary or "").strip()
    if not text:
        return "not_applicable"
    low = text.lower()
    hits = sum(1 for m in _BOILERPLATE_MARKERS if m in low)
    if hits >= 2:
        return "high"
    if hits == 1:
        return "medium"
    return "low"


def load_publication_policy(path: str | Path | None = None) -> dict:
    """publication_policy.yaml → dict. 없으면 보수적 기본(전문 게시 금지, preview 200)."""
    import yaml

    p = Path(path) if path else _PUBLICATION_POLICY_PATH
    if not p.exists():
        return {"default": {"max_public_preview_chars": 200}, "per_source": {}}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def publication_policy_for(source_id: str, policy: dict) -> str:
    """소스별 게시 정책 문자열. preview 0이면 no_public_preview(내부 시그널 전용)."""
    default = policy.get("default", {}) or {}
    per = (policy.get("per_source", {}) or {}).get(source_id, {}) or {}
    chars = per.get("max_public_preview_chars", default.get("max_public_preview_chars", 200))
    if chars == 0:
        return "no_public_preview"
    return f"preview_only:{chars}"


def _structured_signal(candidate: ArticleCandidate, purpose: Optional[str]) -> bool:
    return (
        candidate.numeric_payload_exempt
        or purpose in ("numeric", "trend")
    )


def evaluate_pre_gate(
    candidate: ArticleCandidate,
    *,
    purpose: Optional[str] = None,
    source_group: Optional[str] = None,
    confirmation_policy: Optional[str] = None,
    publication_policy: Optional[dict] = None,
    full_threshold: Optional[int] = None,
) -> QualityPreGateResult:
    """candidate 1건의 사전 게이트 판정. decision = reject > hold > pass.

    게이트:
    1) evidence — raw_artifact_path/extracted_text_ref 둘 다 없으면 reject(근거 없음).
    2) identity — title도 structured signal도 없으면 reject(식별 불가).
    3) body — present/partial/numeric_exempt=pass, snippet_only/missing/parser_error=hold,
       malformed=reject.
    4) published_at — 존재하나 파싱 불가면 hold(데이터 품질). 부재는 note만(hold 아님).
    5) boilerplate — high면 hold.
    """
    reasons: list[str] = []
    reject = False
    hold = False

    evidence_ref = candidate.raw_artifact_path or candidate.extracted_text_ref
    structured = _structured_signal(candidate, purpose)

    # 1) evidence
    if not evidence_ref:
        reject = True
        reasons.append("no_evidence_ref")

    # 2) identity
    if not candidate.title and not structured:
        reject = True
        reasons.append("no_title_no_structured_signal")

    # 3) body state
    state = assess_body_state(
        body_text=candidate.body_text, summary=candidate.summary, purpose=purpose,
        numeric_payload_exempt=candidate.numeric_payload_exempt,
        parse_error=candidate.parse_error, full_threshold=full_threshold,
    )
    if state.extraction_status in ("present", "partial", "numeric_exempt"):
        pass
    elif state.extraction_status == "snippet_only":
        hold = True
        reasons.append("body_snippet_only")
    elif state.extraction_status == "missing":
        hold = True
        reasons.append("body_missing")
    elif state.extraction_status == "parser_error":
        hold = True
        reasons.append("parser_error")
    elif state.extraction_status in ("malformed", "no_artifact"):
        reject = True
        reasons.append(f"body_{state.extraction_status}")

    # 4) published_at 정규화
    normalized_pub, pub_err = normalize_published_at(candidate.published_at)
    if candidate.published_at and pub_err:
        hold = True
        reasons.append(f"published_at_unparseable:{pub_err}")
    elif candidate.published_at is None:
        reasons.append("published_at_absent")

    # 5) boilerplate
    boilerplate = assess_boilerplate(candidate)
    if boilerplate == "high":
        hold = True
        reasons.append("boilerplate_suspected")

    decision = "reject" if reject else ("hold" if hold else "pass")
    policy = publication_policy if publication_policy is not None else load_publication_policy()

    return QualityPreGateResult(
        source_id=candidate.source_id,
        candidate_id=None,  # 안정 id는 Phase H(raw_events 승격)에서 부여
        decision=decision,
        reasons=tuple(reasons),
        normalized_published_at=normalized_pub,
        canonical_url=candidate.canonical_url,
        evidence_ref=evidence_ref,
        duplicate_key=compute_duplicate_key(candidate),
        boilerplate_risk=boilerplate,
        publication_policy=publication_policy_for(candidate.source_id, policy),
    )


def summarize_pre_gate(results) -> dict:
    """pass/hold/reject 분포 + 상위 사유 집계(보고용)."""
    decisions = {"pass": 0, "hold": 0, "reject": 0}
    hold_reasons: dict[str, int] = {}
    reject_reasons: dict[str, int] = {}
    for r in results:
        decisions[r.decision] = decisions.get(r.decision, 0) + 1
        bucket = hold_reasons if r.decision == "hold" else (
            reject_reasons if r.decision == "reject" else None
        )
        if bucket is not None:
            for reason in r.reasons:
                key = reason.split(":")[0]
                bucket[key] = bucket.get(key, 0) + 1
    return {
        "decisions": decisions,
        "top_hold_reasons": dict(sorted(hold_reasons.items(), key=lambda x: -x[1])),
        "top_reject_reasons": dict(sorted(reject_reasons.items(), key=lambda x: -x[1])),
    }
