from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from ingestion.orchestration.cycle_planner import SourceSchedule

# Phase C: 오케스트레이션용 소스 프로필. source_registry.yaml(수집 엔진 1차 출처)을
# 수정하지 않고, 반복 운영에 필요한 보강 필드만 별도 YAML(source_profiles.yaml)로 둔다.

_DEFAULT_PROFILES_PATH = Path(__file__).parent.parent / "configs" / "source_profiles.yaml"

# community 소스의 기본 확정 정책 — "단독 확정 금지"(09 D-9). standard로 두면 보정한다.
COMMUNITY_DEFAULT_CONFIRMATION = "unconfirmed_until_corroborated"

_ALLOWED_FIELDS = frozenset({
    "enabled", "purpose", "freshness_bucket", "min_interval_seconds",
    "risk_level", "preferred_strategy", "requires_api_key", "is_community",
    "confirmation_policy", "notes",
})


@dataclass(frozen=True)
class SourceProfile:
    """반복 운영을 위한 소스 메타. 실제 수집 라우팅은 run_collection_probe가 책임진다.

    preferred_strategy는 강제 경로가 아니라 metadata다(03 §3). 불확실한 값은
    conservative default를 쓰고 notes에 명시한다(없는 사실을 만들지 않는다).
    """
    source_id: str
    enabled: bool = True
    purpose: str = "news"              # news|community|trend|numeric|regulatory|search|domain
    freshness_bucket: str = "medium"   # near_real_time|short|medium|daily
    min_interval_seconds: int = 1800
    risk_level: str = "low"            # low|medium|high
    preferred_strategy: Optional[str] = None
    requires_api_key: bool = False
    is_community: bool = False
    confirmation_policy: str = "standard"  # standard|unconfirmed_until_corroborated
    notes: Optional[str] = None


def _profile_from_dict(source_id: str, fields: dict) -> SourceProfile:
    unknown = set(fields) - _ALLOWED_FIELDS
    if unknown:
        raise ValueError(
            f"source profile {source_id!r} has unknown fields: {sorted(unknown)}"
        )
    return SourceProfile(source_id=source_id, **fields)


def load_source_profiles(path: str | Path | None = None) -> list[SourceProfile]:
    """source_profiles.yaml → SourceProfile 목록(YAML 등록 순서 보존).

    필수 키는 ``source_id``(YAML 매핑 키). 알 수 없는 필드는 명확한 ValueError.
    파일 없거나 비면 빈 목록.
    """
    import yaml

    p = Path(path) if path else _DEFAULT_PROFILES_PATH
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    profiles_raw = raw.get("profiles", {})
    if not isinstance(profiles_raw, dict):
        raise ValueError("source_profiles.yaml: 'profiles' must be a mapping")

    out: list[SourceProfile] = []
    for source_id, fields in profiles_raw.items():
        if fields is None:
            fields = {}
        if not isinstance(fields, dict):
            raise ValueError(f"source profile {source_id!r} must be a mapping")
        out.append(_profile_from_dict(str(source_id), fields))
    return out


def profiles_to_schedules(
    profiles: Sequence[SourceProfile],
    last_run_by_source: Optional[dict[str, Optional[datetime]]] = None,
) -> list[SourceSchedule]:
    """SourceProfile → SourceSchedule(Phase B due 판정 입력). 입력 순서 보존.

    last_run_by_source가 주어지면 소스별 last_run_at을 반영한다(없으면 None=즉시 due).
    """
    last_run = last_run_by_source or {}
    return [
        SourceSchedule(
            source_id=p.source_id,
            min_interval_seconds=p.min_interval_seconds,
            last_run_at=last_run.get(p.source_id),
            freshness_bucket=p.freshness_bucket,
            enabled=p.enabled,
        )
        for p in profiles
    ]
