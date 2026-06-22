"""F-12: Production runner 통합 — 주입형 probe(네트워크 0), mirror fallback, 상태/모니터링."""
from __future__ import annotations

import json
import types

from ingestion.orchestration.source_profile import SourceProfile
from ingestion.tools.run_production_orchestration import (
    ProductionRunConfig,
    run_production_orchestration,
)


def _profile(sid, **kw):
    base = dict(source_id=sid, enabled=True, source_group="news", purpose="news",
                live_eligible="true", requires_api_key=False,
                preferred_strategy="strategy_loop_fetch", min_interval_seconds=1800)
    base.update(kw)
    return SourceProfile(**base)


def _fake_probe_factory(tmp_path):
    """source별 JSON artifact를 써두고 raw_payload 경로를 가진 probe_result 반환."""
    def _probe(source_id, *, max_items=5, force=False):
        payload = {"articles": [
            {"title": f"{source_id} headline one", "url": f"https://{source_id}.test/1",
             "publishedAt": "2025-06-02T10:00:00Z"},
            {"title": f"{source_id} headline two", "url": f"https://{source_id}.test/2",
             "publishedAt": "2025-06-02T11:00:00Z"},
        ]}
        p = tmp_path / f"{source_id}_payload.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        paths = types.SimpleNamespace(raw_payload=str(p), extracted_payload=None,
                                      raw_html=None, raw_signal=None)
        return types.SimpleNamespace(status="LIVE_SUCCESS", artifact_paths=paths,
                                     error_category=None, http_status=200)
    return _probe


def _config(tmp_path, mode):
    return ProductionRunConfig(
        mode=mode,
        state_path=tmp_path / "state.json",
        queue_path=tmp_path / "queue.jsonl",
        raw_mirror_path=tmp_path / "raw_mirror.jsonl",
        dedup_index_path=tmp_path / "dedup.json",
        governor_path=tmp_path / "gov.json",
        monitoring_dir=tmp_path / "monitoring",
        all_due=True,
    )


def test_dry_run_no_network_all_sources_have_state(tmp_path):
    profiles = [_profile("bbc"), _profile("ap_news")]
    result = run_production_orchestration(
        _config(tmp_path, "production-dry-run"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=None, write_outputs=False)
    assert result["source_without_state"] == 0
    assert result["unknown_root_cause"] == 0
    assert result["critical_alerts"] == 0
    assert result["summary"]["records_collected"] == 0  # dry-run은 probe 안 함


def test_validation_with_fake_probe_collects_records(tmp_path):
    profiles = [_profile("bbc"), _profile("ap_news")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=_fake_probe_factory(tmp_path), write_outputs=True)
    s = result["summary"]
    assert s["records_collected"] >= 2
    assert s["records_enqueued"] >= 1
    assert result["critical_alerts"] == 0


def test_db_unavailable_falls_back_to_mirror(tmp_path):
    profiles = [_profile("bbc")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=_fake_probe_factory(tmp_path), db_writer=None,
        write_outputs=True)
    assert result["bridge_result"]["target"] == "mirror"
    assert result["raw_events_bridge_contract_pass"] is True
    assert (tmp_path / "raw_mirror.jsonl").exists()


def test_db_writer_used_when_available(tmp_path):
    captured = []
    profiles = [_profile("bbc")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=_fake_probe_factory(tmp_path),
        db_writer=lambda d: captured.append(d) or True, write_outputs=True)
    assert result["bridge_result"]["target"] == "db"
    assert len(captured) >= 1
    # secret이 payload에 없어야 함
    blob = json.dumps(captured).lower()
    assert "api_key=" not in blob and "sk-" not in blob


def test_duplicate_records_collapsed_across_runs(tmp_path):
    from datetime import datetime, timedelta, timezone
    profiles = [_profile("bbc")]
    cfg = _config(tmp_path, "production-validation")
    probe = _fake_probe_factory(tmp_path)
    t0 = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)
    r1 = run_production_orchestration(cfg, profiles=profiles, memory={}, api_ready_map={},
                                      probe_fn=probe, now=t0, write_outputs=True)
    assert r1["summary"]["records_enqueued"] >= 1
    # 두 번째 실행(interval 경과 후) — 같은 source_url → dedup index가 중복 collapse
    r2 = run_production_orchestration(cfg, profiles=profiles, memory={}, api_ready_map={},
                                      probe_fn=probe, now=t0 + timedelta(seconds=2000),
                                      write_outputs=True)
    assert r2["summary"]["duplicates_skipped"] >= 1


def test_monitoring_and_state_written(tmp_path):
    profiles = [_profile("bbc")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=_fake_probe_factory(tmp_path), write_outputs=True)
    assert result["monitoring_written"] is True
    assert result["production_state_written"] is True
    assert (tmp_path / "state.json").exists()
    assert result["monitoring_paths"]["summary_path"]


def test_repeated_failures_quarantine_source(tmp_path):
    # 연속 실패가 consecutive_failure_count를 누적해 임계(3) 도달 시 QUARANTINED로 전이(F-4 배선)
    from datetime import datetime, timedelta, timezone

    def _failing_probe(source_id, *, max_items=5, force=False):
        paths = types.SimpleNamespace(raw_payload=None, extracted_payload=None,
                                      raw_html=None, raw_signal=None)
        return types.SimpleNamespace(status="NETWORK_ERROR", artifact_paths=paths,
                                     error_category="NETWORK_ERROR", http_status=None)

    profiles = [_profile("bbc")]
    cfg = _config(tmp_path, "production-validation")
    t = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)
    final = None
    for i in range(3):
        result = run_production_orchestration(
            cfg, profiles=profiles, memory={}, api_ready_map={},
            probe_fn=_failing_probe, now=t + timedelta(seconds=4000 * i), write_outputs=True)
        final = {s.source_id: s for s in result["states"]}["bbc"]
    assert final.consecutive_failure_count >= 3
    assert final.current_status == "QUARANTINED"
    assert final.quarantine_until is not None


def test_structured_signal_label_not_literal(tmp_path):
    # structured_signal record의 body_state_or_signal은 리터럴이 아니라 실제 signal type
    def _signal_probe(source_id, *, max_items=5, force=False):
        payload = {"values": [{"datetime": "2026-06-14", "close": "101.2"}], "symbol": "AAPL"}
        p = tmp_path / f"{source_id}_sig.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        paths = types.SimpleNamespace(raw_payload=str(p), extracted_payload=None,
                                      raw_html=None, raw_signal=None)
        return types.SimpleNamespace(status="LIVE_SUCCESS", artifact_paths=paths,
                                     error_category=None, http_status=200)

    profiles = [_profile("twelve_data", source_group="market", purpose="numeric")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={"twelve_data": True}, probe_fn=_signal_probe, write_outputs=True)
    # signal record가 생겼다면 label이 "structured_signal" 리터럴이 아니어야 함
    import pathlib
    qp = pathlib.Path(str(_config(tmp_path, "x").queue_path))
    if qp.exists():
        for line in qp.read_text(encoding="utf-8").strip().splitlines():
            rec = json.loads(line)
            if rec["record_type"] == "structured_signal":
                assert rec["body_state_or_signal"] != "structured_signal"


def test_rate_limited_probe_is_external_not_failure(tmp_path):
    # R-GdeltMainLoopResume: provider 429는 코드 실패가 아니라 외부 제한 — quarantine/failure로
    # 집계하지 않고 cooldown으로 기록한다(우회 없음).
    def _rl_probe(source_id, *, max_items=5, force=False):
        paths = types.SimpleNamespace(raw_payload=None, extracted_payload=None,
                                      raw_html=None, raw_signal=None)
        return types.SimpleNamespace(status="RATE_LIMITED", artifact_paths=paths,
                                     error_category=None, http_status=429)

    profiles = [_profile("gdelt", source_group="official")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=_rl_probe, write_outputs=True)
    st = {s.source_id: s for s in result["states"]}["gdelt"]
    assert st.current_status != "QUARANTINED"
    assert st.consecutive_failure_count == 0           # 429 != failure
    assert "gdelt" not in result["summary"]["error_by_source"]
    assert result["critical_alerts"] == 0


def test_probe_exception_isolated(tmp_path):
    def boom(source_id, *, max_items=5, force=False):
        raise RuntimeError("probe boom")
    profiles = [_profile("bbc"), _profile("ap_news")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=boom, write_outputs=True)
    # 예외가 전체를 무너뜨리지 않음 — 실행 완료 + critical 없음
    assert result["critical_alerts"] == 0
    assert "bbc" in result["summary"]["error_by_source"]


# ── C live wiring: event_resolution_sink 결선(주입형, db_writer 와 동일 패턴) ──────────
def test_event_resolution_sink_invoked_with_records_and_clusters(tmp_path):
    # cross-source dedup 직후 sink(written_records, clusters)가 호출되고 결과가 result에 담긴다.
    captured = {}

    def _sink(records, clusters):
        captured["records"] = records
        captured["clusters"] = clusters
        return {"enabled": True, "created": 0, "wired_ok": True}

    profiles = [_profile("bbc"), _profile("ap_news")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=_fake_probe_factory(tmp_path),
        event_resolution_sink=_sink, write_outputs=True)
    assert result["event_resolution"] == {"enabled": True, "created": 0, "wired_ok": True}
    assert "records" in captured                        # written_records 전달됨
    assert isinstance(captured["clusters"], list)       # clusters 전달됨


def test_event_resolution_sink_default_none_preserves_behavior(tmp_path):
    # 미주입(기본) → Event 영속 0(기존 동작 보존). event_cards 경로 무영향.
    profiles = [_profile("bbc")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=_fake_probe_factory(tmp_path), write_outputs=True)
    assert result["event_resolution"] is None
    assert result["critical_alerts"] == 0


def test_event_resolution_sink_failure_isolated(tmp_path):
    # sink 실패가 수집/raw_events bridge 를 무너뜨리지 않는다(격리).
    def _boom_sink(records, clusters):
        raise RuntimeError("sink boom")

    profiles = [_profile("bbc")]
    result = run_production_orchestration(
        _config(tmp_path, "production-validation"), profiles=profiles, memory={},
        api_ready_map={}, probe_fn=_fake_probe_factory(tmp_path),
        event_resolution_sink=_boom_sink, write_outputs=True)
    assert result["event_resolution"] == {"wired": True, "error": "RuntimeError"}
    assert result["critical_alerts"] == 0
    assert result["raw_events_bridge_contract_pass"] is True
