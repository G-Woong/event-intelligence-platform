"""ArticleCandidate 모델 (Phase D-2, 설계 05 §2).

source-level seed가 artifact를 갖는 경우, artifact를 파싱해 얻는 **개별 기사 단위 후보**.
아직 raw_events가 아니다(Phase H에서 승격). 핵심 원칙: **없는 값을 만들지 않는다** —
title/url/body가 없으면 None이고, body 누락은 ``body_missing=True``로 보존한다(사건은 살린다).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ArticleCandidate:
    source_id: str
    title: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    summary: Optional[str] = None
    body_text: Optional[str] = None
    raw_artifact_path: Optional[str] = None
    extracted_text_ref: Optional[str] = None
    canonical_url: Optional[str] = None
    body_missing: bool = True
    collection_status: str = "UNKNOWN"
    parser_name: str = ""
    parse_error: Optional[str] = None
    numeric_payload_exempt: bool = False
    confirmation_policy: Optional[str] = None
