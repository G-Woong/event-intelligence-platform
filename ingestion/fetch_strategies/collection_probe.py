from __future__ import annotations

import logging
from typing import Optional

from ingestion.fetch_strategies.models import (
    ArtifactPaths,
    CollectionProbeResult,
    ExtractionBundle,
)
from ingestion.probes.api_probe import _PROBE_SPEC, run_api_live_probe
from ingestion.probes.models import ProbeResult
from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS

logger = logging.getLogger("ingestion.fetch_strategies.collection_probe")

# Hardcoded fallback frozenset — sources that always go to CloudBrowserLikeStrategy
# regardless of _SERVICE_CONFIGS. New sites should be added to playwright_probe_sites.yaml
# (deferred=false) instead of this set — _is_playwright_required() picks them up automatically.
_PLAYWRIGHT_FIRST_SOURCES = frozenset({
    "krx_kind", "eu_press_corner", "signal_bz", "loword",
    "google_trending_now", "dcinside", "fmkorea",
})


def run_collection_probe(
    source_id: str,
    query: Optional[str] = None,
    max_items: int = 5,
    force: bool = False,
) -> CollectionProbeResult:
    """Agent top-level entry: route source to the right probe strategy.

    Routing priority:
    1. Source has _PROBE_SPEC entry (API-probed service) → run_api_live_probe
    2. Playwright-required or external-signal sources → CloudBrowserLikeStrategy
    3. Fallback: strategy loop on base_url from _SERVICE_CONFIGS

    A health gate runs first (skip terminal-blocked / cooling-down / quarantined
    sources without any network call). force=True bypasses the gate.
    """
    gated = _health_gate(source_id, force=force)
    if gated is not None:
        return gated

    service_config = _SERVICE_CONFIGS.get(source_id)
    has_probe_spec = source_id in _PROBE_SPEC

    # Route 1: has probe spec → use api probe
    if has_probe_spec and source_id not in _PLAYWRIGHT_FIRST_SOURCES:
        # query 없으면 기존 호출 형태 유지 (하위호환 — 기존 mock 단언 보존)
        if query:
            probe_result = run_api_live_probe(source_id, max_calls=1, query=query)
        else:
            probe_result = run_api_live_probe(source_id, max_calls=1)
        return _update_health(CollectionProbeResult(
            source_id=source_id,
            status=probe_result.status,
            strategy_used="api",
            items_found=probe_result.items_found,
            probe_result=probe_result,
            artifact_paths=_probe_artifact_paths(probe_result),
            error_category=probe_result.error_category,
            next_action=probe_result.next_action,
        ))

    # Route 2: Playwright-required or external-signal
    if source_id in _PLAYWRIGHT_FIRST_SOURCES or _is_playwright_required(source_id, service_config):
        # site spec 보유 소스는 run_playwright_probe로 위임 — URL 템플릿/wait 힌트/
        # selector 추출/click-through/429 기록을 단일 경로로 통일 (docs/RISK-S05 구조 수정).
        site_spec = None
        try:
            from ingestion.probes.site_specs import load_site_specs
            site_spec = load_site_specs().get(source_id)
        except Exception:
            pass
        if site_spec is not None and not site_spec.deferred:
            from ingestion.probes.playwright_probe import run_playwright_probe
            probe_result = run_playwright_probe(
                source_id, query=query, max_items=max_items
            )
            ap = probe_result.artifact_paths or {}
            return _update_health(CollectionProbeResult(
                source_id=source_id,
                status=probe_result.status,
                strategy_used="playwright_site_spec",
                items_found=probe_result.items_found,
                probe_result=probe_result,
                artifact_paths=ArtifactPaths(
                    raw_payload=ap.get("raw_signal"),
                    screenshot=ap.get("screenshot"),
                    rendered_dom=ap.get("rendered_dom"),
                ),
                error_category=probe_result.error_category,
                next_action=probe_result.next_action,
            ))

        # site spec 없는(또는 deferred) playwright 소스만 기존 generic 렌더 경로 유지
        endpoint = (service_config or {}).get("endpoint", "")
        if not endpoint:
            return CollectionProbeResult(
                source_id=source_id,
                status="UNKNOWN",
                error_category="no_endpoint",
                next_action="add_endpoint_to_service_config",
            )
        from ingestion.fetch_strategies.cloud_browser_like import CloudBrowserLikeStrategy
        rendered = CloudBrowserLikeStrategy().fetch(endpoint, source_id)
        bundle = ExtractionBundle(rendered_page=rendered, markdown=rendered.markdown)
        return _update_health(CollectionProbeResult(
            source_id=source_id,
            status=rendered.status,
            strategy_used=rendered.strategy_used,
            items_found=1 if rendered.html else 0,
            extraction=bundle,
            error_category=(
                rendered.error_category.value if rendered.error_category else None
            ),
            next_action=(
                "integrate_into_pipeline"
                if rendered.status == "LIVE_SUCCESS"
                else "investigate"
            ),
        ))

    # Route 3: fallback strategy loop on base URL
    base_url = (service_config or {}).get("endpoint", "")
    if not base_url:
        return CollectionProbeResult(
            source_id=source_id,
            status="UNKNOWN",
            error_category="no_endpoint",
            next_action="add_endpoint_to_service_config",
        )

    from ingestion.fetch_strategies.strategy_runner import run_fetch_strategy_loop
    loop_result = run_fetch_strategy_loop(
        source_id, base_url, source_spec=service_config or {}, query=query or ""
    )
    status = _loop_status_to_probe_status(loop_result.status)
    return _update_health(CollectionProbeResult(
        source_id=source_id,
        status=status,
        strategy_used=(
            loop_result.attempts[-1].strategy if loop_result.attempts else ""
        ),
        items_found=1 if loop_result.final_html else 0,
        attempts=loop_result.attempts,
        error_category=(
            loop_result.final_error_type.value
            if loop_result.final_error_type
            else None
        ),
        next_action=(
            "integrate_into_pipeline" if status == "LIVE_SUCCESS" else "investigate"
        ),
    ))


def _health_gate(source_id: str, force: bool = False) -> Optional[CollectionProbeResult]:
    """Pre-probe gate: return a no-network result for unhealthy sources.

    BLOCKED_TERMINAL → BLOCKED, cooldown/quarantine(미래 deadline) → RATE_LIMITED,
    DEFERRED_SPECIAL_ROUND → DEFERRED. force=True bypasses (수동 unquarantine 점검용).
    """
    if force:
        return None
    try:
        from ingestion.core.source_health import get_health_store, should_skip
        state = get_health_store().get(source_id)
    except Exception:
        return None
    skip, reason = should_skip(state)
    if not skip:
        return None
    if state.state == "BLOCKED_TERMINAL":
        status = "BLOCKED"
    elif state.state == "DEFERRED_SPECIAL_ROUND":
        status = "DEFERRED"
    else:
        status = "RATE_LIMITED"
    logger.info("Health gate skip for %s: %s", source_id, reason)
    return CollectionProbeResult(
        source_id=source_id,
        status=status,
        error_category=state.last_error_category or state.state,
        next_action=f"health_gate_skip:{reason}",
    )


def _update_health(result: CollectionProbeResult) -> CollectionProbeResult:
    """Persist probe outcome into the health store. Never raises."""
    try:
        from ingestion.core.source_health import apply_probe_outcome, get_health_store
        store = get_health_store()
        prev = store.get(result.source_id)
        next_retry_at = None
        if result.probe_result is not None:
            next_retry_at = result.probe_result.next_retry_at
        new_state = apply_probe_outcome(
            prev,
            source_id=result.source_id,
            status=result.status,
            error_category=result.error_category,
            next_retry_at=next_retry_at,
        )
        store.set(new_state)
    except Exception as exc:
        logger.warning("health store update failed for %s: %s", result.source_id, exc)
    return result


def _is_playwright_required(source_id: str, service_config: Optional[dict]) -> bool:
    """Return True if source should use CloudBrowserLikeStrategy.

    Checks both the service_config status_override field (legacy) and the
    playwright_probe_sites.yaml (deferred=false entries), so new playwright sites
    can be registered in YAML without touching this code.
    """
    # Legacy status_override check
    if service_config and service_config.get("status_override") in (
        "PLAYWRIGHT_REQUIRED", "EXTERNAL_SIGNAL_SOURCE"
    ):
        return True

    # YAML-driven check: site exists in playwright_probe_sites.yaml and is NOT deferred
    try:
        from ingestion.probes.site_specs import load_site_specs
        specs = load_site_specs()
        spec = specs.get(source_id)
        if spec and not spec.deferred and spec.collection_method == "playwright":
            return True
    except Exception:
        pass

    return False


def _probe_artifact_paths(probe_result: ProbeResult) -> ArtifactPaths:
    ap = probe_result.artifact_paths
    return ArtifactPaths(
        raw_payload=ap.get("raw_payload"),
        extracted_payload=ap.get("extracted_payload"),
        screenshot=ap.get("screenshot"),
    )


def _loop_status_to_probe_status(loop_status: str) -> str:
    return {
        "success": "LIVE_SUCCESS",
        "cached": "LIVE_SUCCESS",
        "blocked": "BLOCKED",
        "exhausted": "NETWORK_ERROR",
        "rate_limited": "RATE_LIMITED",
    }.get(loop_status, "UNKNOWN")
