"""source-level seed → article-level candidates 확장 (Phase D-4, 설계 05 §3.5).

EventSeedCandidate(seed)를 받아 artifact를 읽고 개별 기사 후보로 분해한다. 분해 불가능하면
seed 단서(제목/URL/시각)로 **source-level fallback 후보**를 만들어 사건을 보존한다(04 §10).
실패 seed는 기본적으로 확장하지 않는다. 네트워크 redirect 해석은 기본 off다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.artifact_parser import parse_artifact_text
from ingestion.orchestration.canonical_url import canonicalize_url
from ingestion.orchestration.event_seed import SUCCESS_STATUSES


@dataclass(frozen=True)
class CandidateExpansionReport:
    source_id: str
    candidates: list[ArticleCandidate] = field(default_factory=list)
    parser_name: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    fallback_used: bool = False
    source_level_fallback: bool = False


def _fmt_from_path(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    if ext == ".json":
        return "json"
    if ext == ".xml":
        return "xml"
    if ext == ".txt":
        return "extracted_text"
    return None


def _source_level_candidate(seed: dict, confirmation_policy: Optional[str],
                            *, parse_error: Optional[str] = None) -> ArticleCandidate:
    """artifact가 없거나 분해 불가일 때 seed 단서로 사건을 보존하는 후보."""
    url = seed.get("source_url")
    return ArticleCandidate(
        source_id=seed.get("source_id", ""),
        title=seed.get("title_or_keyword") or None,
        source_url=url or None,
        published_at=seed.get("timestamp"),
        summary=None,
        body_text=None,
        raw_artifact_path=seed.get("raw_artifact_path"),
        extracted_text_ref=seed.get("extracted_text_ref"),
        canonical_url=canonicalize_url(url),
        body_missing=True,
        collection_status=seed.get("collection_status", "UNKNOWN"),
        parser_name="source_level_fallback",
        parse_error=parse_error,
        numeric_payload_exempt=False,
        confirmation_policy=confirmation_policy,
    )


def expand_seed_to_article_candidates(
    seed: dict,
    *,
    artifact_root: Optional[Path] = None,
    allow_network_resolution: bool = False,
    confirmation_policy: Optional[str] = None,
) -> CandidateExpansionReport:
    """seed → ArticleCandidate 목록. 분해 불가 시 source-level fallback.

    - 실패 seed(collection_status not in SUCCESS)는 확장하지 않는다.
    - artifact 경로 없음/파일 없음/빈 파일/파싱 실패 → fallback 후보 + errors 보존.
    - ``allow_network_resolution=True``일 때만 canonical_url을 네트워크 resolver로 승격한다(기본 off).
    """
    source_id = seed.get("source_id", "")
    policy = confirmation_policy or seed.get("confirmation_policy")
    status = seed.get("collection_status", "UNKNOWN")

    if status not in SUCCESS_STATUSES:
        return CandidateExpansionReport(
            source_id=source_id, candidates=[], parser_name=None,
            errors=["non_success_seed_not_expanded"], fallback_used=False,
            source_level_fallback=False,
        )

    artifact_path = seed.get("raw_artifact_path") or seed.get("extracted_text_ref")
    if not artifact_path:
        return CandidateExpansionReport(
            source_id=source_id, candidates=[_source_level_candidate(seed, policy)],
            parser_name="source_level_fallback", errors=["no_artifact_path"],
            fallback_used=True, source_level_fallback=True,
        )

    path = Path(artifact_path)
    if artifact_root is not None and not path.is_absolute():
        path = Path(artifact_root) / path
    if not path.exists():
        return CandidateExpansionReport(
            source_id=source_id, candidates=[_source_level_candidate(seed, policy)],
            parser_name="source_level_fallback", errors=["artifact_file_missing"],
            fallback_used=True, source_level_fallback=True,
        )

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return CandidateExpansionReport(
            source_id=source_id,
            candidates=[_source_level_candidate(seed, policy, parse_error=str(exc))],
            parser_name="source_level_fallback", errors=[f"read_error: {exc}"],
            fallback_used=True, source_level_fallback=True,
        )

    candidates, parser_name, errors = parse_artifact_text(
        text, source_id=source_id, collection_status=status,
        confirmation_policy=policy, raw_artifact_path=str(path),
        fmt=_fmt_from_path(path),
    )

    if not candidates:
        # 빈/깨진/인식불가 artifact → 사건은 보존(fallback).
        return CandidateExpansionReport(
            source_id=source_id, candidates=[_source_level_candidate(seed, policy)],
            parser_name="source_level_fallback", errors=errors or ["no_candidates"],
            fallback_used=True, source_level_fallback=True,
        )

    if allow_network_resolution:
        candidates = [_resolve_canonical(c) for c in candidates]

    return CandidateExpansionReport(
        source_id=source_id, candidates=candidates, parser_name=parser_name,
        errors=errors, fallback_used=False, source_level_fallback=False,
    )


def _resolve_canonical(candidate: ArticleCandidate) -> ArticleCandidate:
    """opt-in 네트워크 canonical 해석. 기본 경로에서는 호출되지 않는다."""
    if not candidate.source_url:
        return candidate
    from dataclasses import replace

    from ingestion.tools.url_resolver import resolve
    new_canonical = canonicalize_url(
        candidate.source_url, allow_network_resolution=True, resolver=resolve
    )
    return replace(candidate, canonical_url=new_canonical)
