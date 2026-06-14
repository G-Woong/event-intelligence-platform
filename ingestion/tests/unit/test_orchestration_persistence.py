"""Phase B 상태 영속화 + EventSeedCandidate 확장필드 안정성 테스트 (docs 05, 08).

local_file state는 새 store 인스턴스(프로세스 재시작 모사)에서도 값이 유지됨을 검증한다.
Redis backend는 사용하지 않는다. temp path만 쓴다(production state를 더럽히지 않음).
"""
from __future__ import annotations

from ingestion.core.rate_limit_store import LocalPersistentRateLimitStore
from ingestion.core.source_health import (
    HEALTHY,
    LocalFileSourceHealthStore,
    SourceHealthState,
)
from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.orchestration.event_seed import to_event_seed


# ── B-1: local_file state roundtrip ──────────────────────────────────────────

def test_source_health_local_file_roundtrip(tmp_path):
    """write → new store instance → read → same value."""
    p = tmp_path / "health.json"
    store1 = LocalFileSourceHealthStore(p)
    store1.set(SourceHealthState(
        source_id="gdelt", state=HEALTHY, failure_count=2, last_status="LIVE_SUCCESS",
    ))

    store2 = LocalFileSourceHealthStore(p)  # 프로세스 재시작 모사
    got = store2.get("gdelt")
    assert got is not None
    assert got.state == HEALTHY
    assert got.failure_count == 2
    assert got.last_status == "LIVE_SUCCESS"


def test_rate_limit_local_file_roundtrip(tmp_path):
    """cooldown deadline + 호출 기록이 새 인스턴스에서도 유지된다."""
    p = tmp_path / "rate_limit_cache.json"
    s1 = LocalPersistentRateLimitStore(p)
    s1.set_next_retry_at("yna", "2026-06-14T12:00:00Z", reason="429")
    s1.record("yna")

    s2 = LocalPersistentRateLimitStore(p)  # 프로세스 재시작 모사
    assert s2.get_next_retry_at("yna") == "2026-06-14T12:00:00Z"
    assert s2.age_seconds("yna") is not None  # 기록이 살아 있음


def test_health_store_uses_temp_path_not_production(tmp_path):
    """temp path 주입 시 기본 production 파일을 건드리지 않는다."""
    p = tmp_path / "isolated.json"
    store = LocalFileSourceHealthStore(p)
    store.set(SourceHealthState(source_id="x", state=HEALTHY))
    assert p.exists()
    assert str(p) != str(LocalFileSourceHealthStore()._path)


# ── B-3: EventSeedCandidate 확장필드 안정성 ───────────────────────────────────

def test_seed_handles_missing_artifact_paths():
    """artifact 경로가 없으면 None으로 안정 처리(없는 데이터를 만들지 않음)."""
    r = CollectionProbeResult(source_id="gdelt", status="LIVE_SUCCESS", items_found=2)
    seed = to_event_seed(r, query=None, cycle_id="c", timestamp="t")
    assert seed["raw_artifact_path"] is None
    assert seed["extracted_text_ref"] is None
    assert seed["canonical_url"] is None
    assert seed["items_extracted"] is None
    assert seed["body_missing"] is False  # items_found>0 → 본문 있음


def test_seed_body_missing_true_when_zero_items():
    """LIVE_SUCCESS이지만 items_found==0이면 body_missing=True (실패 아님)."""
    r = CollectionProbeResult(source_id="gdelt", status="LIVE_SUCCESS", items_found=0)
    seed = to_event_seed(r, query=None, cycle_id="c", timestamp="t")
    assert seed["body_missing"] is True
    assert seed["collection_status"] == "LIVE_SUCCESS"


def test_seed_reflects_artifact_paths_when_present():
    r = CollectionProbeResult(
        source_id="yna", status="LIVE_SUCCESS", items_found=3,
        artifact_paths=ArtifactPaths(
            raw_payload="/raw/yna.xml", extracted_payload="/ext/yna.json",
        ),
    )
    seed = to_event_seed(r, query=None, cycle_id="c", timestamp="t")
    assert seed["raw_artifact_path"] == "/raw/yna.xml"
    assert seed["extracted_text_ref"] == "/ext/yna.json"


def test_seed_preserves_error_type_and_items_extracted():
    from ingestion.probes.models import ProbeResult

    pr = ProbeResult(
        source_id="gdelt", method="api", status="LIVE_SUCCESS",
        items_found=5, items_extracted=4,
    )
    r = CollectionProbeResult(
        source_id="gdelt", status="LIVE_SUCCESS", items_found=5,
        probe_result=pr, error_category=None,
    )
    seed = to_event_seed(r, query=None, cycle_id="c", timestamp="t")
    assert seed["items_extracted"] == 4
    assert seed["error_type"] is None


def test_seed_raw_signal_fallback_for_playwright():
    """raw_payload 없고 raw_signal만 있으면(playwright site spec) 그것을 쓴다."""
    r = CollectionProbeResult(
        source_id="signal_bz", status="LIVE_SUCCESS", items_found=1,
        artifact_paths=ArtifactPaths(raw_signal="/sig/signal_bz.json"),
    )
    seed = to_event_seed(r, query=None, cycle_id="c", timestamp="t")
    assert seed["raw_artifact_path"] == "/sig/signal_bz.json"
