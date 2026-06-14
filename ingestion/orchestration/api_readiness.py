"""API key readiness audit (Phase D-0, 설계 02/12).

requires_api_key 소스가 실제 ``.env`` 기준으로 live 검증 가능한 상태인지 분류한다.
**키 값은 절대 읽거나 출력하지 않는다** — 존재 여부(present/missing)와 키 *이름*만 다룬다.
소스→필요 키 매핑은 ``_SERVICE_CONFIGS[sid]["keys"]``(수집 엔진 정본)를 재사용하고,
존재 판정은 ``env_loader.env_status``(alias 해석 내장)에 위임한다.

readiness_status:
- ``not_required`` — 키 불필요(공개 엔드포인트).
- ``ready``       — 필요한 키가 모두 정식 이름으로 존재.
- ``ambiguous``   — 존재하지만 일부가 alias 이름으로만 존재(이름 불일치 경고).
- ``missing``     — 필요한 키 중 하나 이상이 완전히 부재.
- ``unknown``     — requires_api_key지만 _SERVICE_CONFIGS에 키 정의가 없음(probe 미연결).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from ingestion.core.env_loader import _ALIASES, env_status, load_env
from ingestion.orchestration.source_profile import SourceProfile

# live smoke를 키 외 정책으로 막아야 하는 사유(우회 금지 대상).
_POLICY_BLOCKED_SKIP_REASONS = frozenset({
    "login_wall_no_bypass", "paywall_no_bypass", "robots_or_policy_block",
    "disabled_by_policy",
})


@dataclass(frozen=True)
class ApiKeyReadiness:
    source_id: str
    required_keys: tuple[str, ...]
    keys_present: bool
    missing_keys: tuple[str, ...]
    alias_warning: tuple[str, ...]
    readiness_status: str  # not_required|ready|ambiguous|missing|unknown
    safe_to_live_smoke: bool


def _service_keys(source_id: str) -> Optional[tuple[str, ...]]:
    """소스가 필요로 하는 env 키 이름들. _SERVICE_CONFIGS 미등록이면 None."""
    try:
        from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS
    except ImportError:
        # 레지스트리 모듈 자체가 없을 때만 None(미연결). 다른 예외는 숨기지 않는다.
        return None
    cfg = _SERVICE_CONFIGS.get(source_id)
    if cfg is None:
        return None
    return tuple(cfg.get("keys", []) or [])


def _present_key_names(env_path: Optional[Path]) -> set[str]:
    """현재 환경에 존재하는 env 변수 *이름* 집합. 값은 사용/노출하지 않는다."""
    loaded = load_env(env_path)  # name→value; 이름만 사용
    return set(os.environ.keys()) | set(loaded.keys())


def _policy_blocked(profile: SourceProfile) -> bool:
    if profile.profile_status == "blocked_policy":
        return True
    return profile.skip_reason in _POLICY_BLOCKED_SKIP_REASONS


def audit_api_key_readiness(
    profiles: Sequence[SourceProfile],
    *,
    env_path: Optional[Path] = None,
) -> list[ApiKeyReadiness]:
    """프로필 목록의 키 준비 상태를 감사한다(입력 순서 보존). 값 비노출."""
    present_names = _present_key_names(env_path)
    out: list[ApiKeyReadiness] = []

    for p in profiles:
        keys = _service_keys(p.source_id)

        # _SERVICE_CONFIGS 미등록 + 키 필요 → unknown(probe 미연결).
        if keys is None:
            status = "unknown" if p.requires_api_key else "not_required"
            out.append(ApiKeyReadiness(
                source_id=p.source_id, required_keys=(), keys_present=False,
                missing_keys=(), alias_warning=(), readiness_status=status,
                safe_to_live_smoke=False,
            ))
            continue

        if not keys:
            # 키 불필요 — live smoke 가능 여부는 정책 차단/enabled로만 결정.
            safe = p.enabled and not _policy_blocked(p)
            out.append(ApiKeyReadiness(
                source_id=p.source_id, required_keys=(), keys_present=True,
                missing_keys=(), alias_warning=(), readiness_status="not_required",
                safe_to_live_smoke=safe,
            ))
            continue

        # env_status로 present/missing 판정(alias 해석 포함), direct/alias 구분은 이름 집합으로.
        status_map = env_status(list(keys), env_path)
        missing = tuple(k for k in keys if status_map.get(k) == "missing")
        alias_warning: list[str] = []
        for k in keys:
            if status_map.get(k) != "present":
                continue
            if k in present_names:
                continue  # 정식 이름으로 존재
            used_alias = next((a for a in _ALIASES.get(k, []) if a in present_names), None)
            if used_alias:
                alias_warning.append(f"{k}<-{used_alias}")

        keys_present = not missing
        if missing:
            readiness = "missing"
        elif alias_warning:
            readiness = "ambiguous"
        else:
            readiness = "ready"

        safe = keys_present and p.enabled and not _policy_blocked(p)
        out.append(ApiKeyReadiness(
            source_id=p.source_id, required_keys=keys, keys_present=keys_present,
            missing_keys=missing, alias_warning=tuple(alias_warning),
            readiness_status=readiness, safe_to_live_smoke=safe,
        ))
    return out


def summarize_readiness(results: Sequence[ApiKeyReadiness]) -> dict[str, int]:
    """ready/missing/ambiguous/not_required/unknown 카운트 요약(보고용)."""
    summary = {"ready": 0, "missing": 0, "ambiguous": 0, "not_required": 0, "unknown": 0}
    for r in results:
        summary[r.readiness_status] = summary.get(r.readiness_status, 0) + 1
    return summary
