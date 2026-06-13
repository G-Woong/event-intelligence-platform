from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_POLICY_PATH = Path(__file__).parent.parent / "configs" / "publication_policy.yaml"


@dataclass
class PublicationPolicy:
    allow_full_text_publication: bool = False
    max_public_preview_chars: int = 200
    attribution_required: bool = True
    source_url_required: bool = True
    raw_artifact_visibility: str = "internal_only"
    quota_limit_notes: str = ""


def load_publication_policy(source_id: str) -> PublicationPolicy:
    """Merge default + per_source overrides (rate_limit_policy와 동일 패턴).

    yaml 부재/손상 시 보수적 기본값으로 동작 — 예외를 올리지 않는다.
    """
    try:
        import yaml
        with open(_POLICY_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception:
        return PublicationPolicy()

    default_cfg: dict = raw.get("default", {})
    per_source_cfg: dict = (raw.get("per_source") or {}).get(source_id, {})
    merged = {**default_cfg, **per_source_cfg}
    return PublicationPolicy(
        allow_full_text_publication=bool(merged.get("allow_full_text_publication", False)),
        max_public_preview_chars=int(merged.get("max_public_preview_chars", 200)),
        attribution_required=bool(merged.get("attribution_required", True)),
        source_url_required=bool(merged.get("source_url_required", True)),
        raw_artifact_visibility=str(merged.get("raw_artifact_visibility", "internal_only")),
        quota_limit_notes=str(merged.get("quota_limit_notes", "")),
    )


def public_preview(text: str, source_id: str) -> str:
    """게시용 프리뷰 절단. 전문 게시가 허용되지 않는 한 max chars로 자른다."""
    if not text:
        return ""
    policy = load_publication_policy(source_id)
    if policy.allow_full_text_publication:
        return text
    limit = policy.max_public_preview_chars
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def is_publication_candidate(item: dict) -> tuple[bool, str]:
    """게시 후보 판정. source_url 필수 — 원문 링크 없는 항목은 게시 불가."""
    source_id = item.get("source_id", "")
    policy = load_publication_policy(source_id)
    if policy.source_url_required and not item.get("source_url"):
        return False, "missing_source_url"
    if policy.attribution_required and not (item.get("source_name") or source_id):
        return False, "missing_attribution"
    return True, ""


def raw_artifact_is_internal(source_id: str) -> bool:
    """raw artifact(raw_html/raw_payload/screenshot)는 외부 노출 금지인가."""
    return load_publication_policy(source_id).raw_artifact_visibility == "internal_only"
