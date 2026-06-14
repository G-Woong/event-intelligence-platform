"""Key-ready + public 소스 제한 live smoke 감사 (Phase D-1).

각 소스를 **1회만**, ``force=False``(health gate 존중), ``max_items`` 최소로 호출한다.
키 부재/정책 차단/비적격 소스는 호출하지 않고 사유와 함께 skip한다(no bypass, rate-limit 존중).
단위 테스트는 fake probe로 결정적 검증하고, 실제 live는 CLI/스크립트로만 수행한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from ingestion.fetch_strategies.collection_probe import run_collection_probe
from ingestion.orchestration.api_readiness import ApiKeyReadiness
from ingestion.orchestration.event_seed import SUCCESS_STATUSES, to_event_seed
from ingestion.orchestration.source_profile import SourceProfile
from ingestion.pipeline.event_queue import EventQueue

_POLICY_BLOCKED_SKIP_REASONS = frozenset({
    "login_wall_no_bypass", "paywall_no_bypass", "robots_or_policy_block",
    "disabled_by_policy",
})


@dataclass(frozen=True)
class LiveSmokeResult:
    source_id: str
    attempted: bool
    status: str
    items_found: Optional[int]
    items_extracted: Optional[int]
    enqueued: bool
    artifact_path_present: bool
    skipped_reason: Optional[str]
    error_type: Optional[str]
    requires_api_key: bool
    key_ready: bool


def _key_ready(profile: SourceProfile,
               readiness: Optional[ApiKeyReadiness]) -> bool:
    if readiness is not None:
        return readiness.safe_to_live_smoke
    # readiness 미제공 시 보수적: 키 불필요 소스만 ready로 본다.
    return not profile.requires_api_key


def _skip_reason(profile: SourceProfile, key_ready: bool) -> Optional[str]:
    """호출하지 말아야 할 사유. 없으면 None(=attempt)."""
    if not profile.enabled:
        return "disabled"
    if profile.profile_status == "blocked_policy" or \
            profile.skip_reason in _POLICY_BLOCKED_SKIP_REASONS:
        return profile.skip_reason or "policy_blocked"
    if profile.requires_api_key and not key_ready:
        return "key_missing"
    if profile.live_eligible == "false" and not key_ready:
        return profile.skip_reason or "not_live_eligible"
    return None


def audit_live_smoke(
    profiles: Sequence[SourceProfile],
    *,
    probe_fn: Callable[..., object] = run_collection_probe,
    readiness_by_source: Optional[dict[str, ApiKeyReadiness]] = None,
    queue: Optional[EventQueue] = None,
    max_items: int = 1,
    force: bool = False,
    enqueue: bool = True,
) -> list[LiveSmokeResult]:
    """프로필 목록에 제한 live smoke를 수행/판정한다(입력 순서 보존)."""
    readiness_by_source = readiness_by_source or {}
    results: list[LiveSmokeResult] = []

    for p in profiles:
        key_ready = _key_ready(p, readiness_by_source.get(p.source_id))
        skip = _skip_reason(p, key_ready)
        if skip is not None:
            results.append(LiveSmokeResult(
                source_id=p.source_id, attempted=False, status="SKIPPED",
                items_found=None, items_extracted=None, enqueued=False,
                artifact_path_present=False, skipped_reason=skip, error_type=None,
                requires_api_key=p.requires_api_key, key_ready=key_ready,
            ))
            continue

        try:
            result = probe_fn(p.source_id, max_items=max_items, force=force)
            ap = getattr(result, "artifact_paths", None)
            artifact_present = bool(ap and ap.to_dict()) if ap is not None else False
            pr = getattr(result, "probe_result", None)
            items_extracted = pr.items_extracted if pr is not None else None
            enqueued = False
            if enqueue and queue is not None and result.status in SUCCESS_STATUSES:
                seed = to_event_seed(
                    result, query=None, cycle_id="live_smoke",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                queue.enqueue(seed)
                enqueued = True
            results.append(LiveSmokeResult(
                source_id=p.source_id, attempted=True, status=result.status,
                items_found=result.items_found, items_extracted=items_extracted,
                enqueued=enqueued, artifact_path_present=artifact_present,
                skipped_reason=None, error_type=result.error_category,
                requires_api_key=p.requires_api_key, key_ready=key_ready,
            ))
        except Exception as exc:  # 소스 격리: 한 소스 예외가 감사를 멈추지 않음
            results.append(LiveSmokeResult(
                source_id=p.source_id, attempted=True, status="CYCLE_ERROR",
                items_found=None, items_extracted=None, enqueued=False,
                artifact_path_present=False, skipped_reason=None, error_type=str(exc),
                requires_api_key=p.requires_api_key, key_ready=key_ready,
            ))
    return results


def summarize_live_smoke(results: Sequence[LiveSmokeResult]) -> dict[str, int]:
    """attempted/success/rate_limited/failed/skipped/artifact 카운트(보고용)."""
    summary = {
        "attempted": 0, "success": 0, "rate_limited": 0, "failed": 0,
        "skipped": 0, "artifact_present": 0, "enqueued": 0,
    }
    for r in results:
        if not r.attempted:
            summary["skipped"] += 1
            continue
        summary["attempted"] += 1
        if r.status in SUCCESS_STATUSES:
            summary["success"] += 1
        elif r.status == "RATE_LIMITED":
            summary["rate_limited"] += 1
        else:
            summary["failed"] += 1
        if r.artifact_path_present:
            summary["artifact_present"] += 1
        if r.enqueued:
            summary["enqueued"] += 1
    return summary
