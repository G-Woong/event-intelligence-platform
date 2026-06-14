"""Phase D-1: live smoke audit (fake probe — 결정적, 네트워크 없음)."""
from __future__ import annotations

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.orchestration.api_readiness import ApiKeyReadiness
from ingestion.orchestration.live_smoke_audit import (
    audit_live_smoke,
    summarize_live_smoke,
)
from ingestion.orchestration.source_profile import SourceProfile


class FakeQueue:
    def __init__(self):
        self.items = []

    def enqueue(self, item):
        self.items.append(item)
        return f"id-{len(self.items)}"


def _ready(source_id, safe=True):
    return ApiKeyReadiness(
        source_id=source_id, required_keys=("K",), keys_present=safe,
        missing_keys=() if safe else ("K",), alias_warning=(),
        readiness_status="ready" if safe else "missing", safe_to_live_smoke=safe,
    )


def _success(sid, **kw):
    return CollectionProbeResult(
        source_id=sid, status="LIVE_SUCCESS", items_found=2,
        artifact_paths=ArtifactPaths(raw_payload=f"/raw/{sid}"),
    )


def test_key_ready_source_attempted():
    p = SourceProfile(source_id="finnhub", requires_api_key=True, live_eligible="false")
    res = audit_live_smoke(
        [p], probe_fn=_success,
        readiness_by_source={"finnhub": _ready("finnhub", True)},
    )[0]
    assert res.attempted is True
    assert res.status == "LIVE_SUCCESS"
    assert res.key_ready is True
    assert res.artifact_path_present is True


def test_key_missing_source_skipped():
    p = SourceProfile(source_id="finnhub", requires_api_key=True, live_eligible="false")
    res = audit_live_smoke(
        [p], probe_fn=_success,
        readiness_by_source={"finnhub": _ready("finnhub", False)},
    )[0]
    assert res.attempted is False
    assert res.skipped_reason == "key_missing"


def test_blocked_source_skipped():
    p = SourceProfile(
        source_id="reuters", enabled=False, profile_status="blocked_policy",
        skip_reason="paywall_no_bypass",
    )
    res = audit_live_smoke([p], probe_fn=_success)[0]
    assert res.attempted is False
    assert res.skipped_reason in ("paywall_no_bypass", "disabled")


def test_rate_limited_source_recorded():
    def rate_limited(sid, **kw):
        return CollectionProbeResult(
            source_id=sid, status="RATE_LIMITED", items_found=0,
            error_category="RATE_LIMITED",
        )

    p = SourceProfile(source_id="gdelt", requires_api_key=False, live_eligible="true")
    res = audit_live_smoke([p], probe_fn=rate_limited)[0]
    assert res.attempted is True
    assert res.status == "RATE_LIMITED"
    summary = summarize_live_smoke([res])
    assert summary["rate_limited"] == 1


def test_no_force_and_no_bypass():
    captured = {}

    def probe(sid, **kw):
        captured.update(kw)
        return _success(sid)

    p = SourceProfile(source_id="yna", requires_api_key=False, live_eligible="true")
    audit_live_smoke([p], probe_fn=probe, max_items=1)
    assert captured.get("force") is False
    assert captured.get("max_items") == 1


def test_public_source_enqueued_on_success():
    q = FakeQueue()
    p = SourceProfile(source_id="yna", requires_api_key=False, live_eligible="true")
    res = audit_live_smoke([p], probe_fn=_success, queue=q)[0]
    assert res.enqueued is True
    assert len(q.items) == 1


def test_disabled_source_skipped():
    p = SourceProfile(source_id="krx_kind", enabled=False, skip_reason="needs_api_integration")
    res = audit_live_smoke([p], probe_fn=_success)[0]
    assert res.attempted is False
    assert res.skipped_reason == "disabled"


def test_isolation_single_source_error_does_not_stop_audit():
    def boom(sid, **kw):
        if sid == "a":
            raise RuntimeError("kaboom")
        return _success(sid)

    profiles = [
        SourceProfile(source_id="a", requires_api_key=False, live_eligible="true"),
        SourceProfile(source_id="b", requires_api_key=False, live_eligible="true"),
    ]
    res = audit_live_smoke(profiles, probe_fn=boom)
    assert res[0].status == "CYCLE_ERROR"
    assert res[1].status == "LIVE_SUCCESS"
