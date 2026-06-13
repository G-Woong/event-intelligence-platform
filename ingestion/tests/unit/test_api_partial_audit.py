"""08 API partial sources E2E audit runner — JSONL schema + 분기 테스트 (네트워크 없음)."""
import os

os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "memory")


_REQUIRED_FIELDS = {
    "run_id", "source_id", "source_role", "root_cause_A_B_C", "output_type",
    "live_called", "collected", "samples_found", "candidates_created",
    "numeric_signals_created", "body_extracted", "body_status",
    "body_artifact_path", "raw_artifact_path", "status", "error_category",
    "next_retry_at", "next_action", "final_status",
}


def _fake_result(status, samples, source_id, raw="ingestion/outputs/raw_payload/x.json"):
    from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult

    cpr = CollectionProbeResult(
        source_id=source_id, status=status, items_found=len(samples),
        artifact_paths=ArtifactPaths(raw_payload=raw),
    )
    return cpr, samples


def _patch(monkeypatch, status, samples, source_id):
    import ingestion.runners.run_api_partial_sources_audit as mod
    cpr, smp = _fake_result(status, samples, source_id)
    monkeypatch.setattr(mod, "run_collection_probe", lambda sid, max_items=3: cpr)
    monkeypatch.setattr(mod, "collect_samples", lambda result, n: smp)
    monkeypatch.setattr(mod, "record_call", lambda *a, **k: None)
    monkeypatch.setattr(mod, "gate_check", lambda sid, q="": None)
    monkeypatch.setattr(mod, "force_local_file_backend", lambda: None)


def test_numeric_source_creates_signals_not_candidates(monkeypatch):
    import ingestion.runners.run_api_partial_sources_audit as mod
    samples = [{"title": "Coal", "snippet": "EIA coal", "published_at": None},
               {"title": "Electricity", "snippet": "survey", "published_at": None}]
    _patch(monkeypatch, "LIVE_SUCCESS", samples, "eia")
    t = next(x for x in mod.TARGETS if x["id"] == "eia")
    rec = mod.audit_source(t, max_items=3, respect_rate_limit=True)
    assert rec["output_type"] == "numeric_signal"
    assert rec["numeric_signals_created"] == 2
    assert rec["candidates_created"] == 0
    assert rec["final_status"] == "PASS"  # min_samples=1
    assert rec["body_status"] == "not_required"


def test_event_source_creates_candidates(monkeypatch):
    import ingestion.runners.run_api_partial_sources_audit as mod
    samples = [{"title": f"doc{i}", "url": None, "published_at": "2026-06-15"} for i in range(3)]
    _patch(monkeypatch, "LIVE_SUCCESS", samples, "culture_info")
    t = next(x for x in mod.TARGETS if x["id"] == "culture_info")
    rec = mod.audit_source(t, max_items=3, respect_rate_limit=True)
    assert rec["candidates_created"] == 3
    assert rec["numeric_signals_created"] == 0
    assert rec["final_status"] == "PASS"  # body_required=False


def test_missing_key_is_deferred_not_pass(monkeypatch):
    import ingestion.runners.run_api_partial_sources_audit as mod
    _patch(monkeypatch, "MISSING_KEY", [], "igdb")
    t = next(x for x in mod.TARGETS if x["id"] == "igdb")
    rec = mod.audit_source(t, max_items=3, respect_rate_limit=True)
    assert rec["final_status"] == "DEFERRED_NEEDS_KEY"
    assert rec["collected"] is False


def test_jsonl_record_has_all_required_fields(monkeypatch):
    import ingestion.runners.run_api_partial_sources_audit as mod
    samples = [{"title": "Coal", "snippet": "x", "published_at": None}]
    _patch(monkeypatch, "LIVE_SUCCESS", samples, "bok_ecos")
    t = next(x for x in mod.TARGETS if x["id"] == "bok_ecos")
    rec = mod.audit_source(t, max_items=3, respect_rate_limit=True)
    assert _REQUIRED_FIELDS.issubset(set(rec.keys()))


def test_flat_numeric_signal_from_quote(tmp_path):
    """finnhub 같은 flat quote(list 아님)에서 단일 numeric_signal 구성."""
    import json
    from ingestion.runners.run_api_partial_sources_audit import _flat_numeric_signal
    p = tmp_path / "finnhub.json"
    p.write_text(json.dumps({"c": 291.13, "h": 297.14, "pc": 295.63, "t": 1781294400}),
                 encoding="utf-8")
    sigs = _flat_numeric_signal("finnhub", str(p))
    assert len(sigs) == 1
    assert sigs[0]["metrics"]["c"] == 291.13
    assert _flat_numeric_signal("finnhub", None) == []


def test_finnhub_flat_quote_branch_passes(monkeypatch, tmp_path):
    import json
    import ingestion.runners.run_api_partial_sources_audit as mod
    raw = tmp_path / "finnhub.json"
    raw.write_text(json.dumps({"c": 291.13, "pc": 295.63}), encoding="utf-8")
    from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
    cpr = CollectionProbeResult(
        source_id="finnhub", status="LIVE_SUCCESS", items_found=1,
        artifact_paths=ArtifactPaths(raw_payload=str(raw)),
    )
    monkeypatch.setattr(mod, "run_collection_probe", lambda sid, max_items=3: cpr)
    monkeypatch.setattr(mod, "collect_samples", lambda result, n: [])  # flat = list 추출 0
    monkeypatch.setattr(mod, "record_call", lambda *a, **k: None)
    monkeypatch.setattr(mod, "gate_check", lambda sid, q="": None)
    t = next(x for x in mod.TARGETS if x["id"] == "finnhub")
    rec = mod.audit_source(t, max_items=3, respect_rate_limit=True)
    assert rec["numeric_signals_created"] == 1
    assert rec["final_status"] == "PASS"


def test_cooldown_skip_records_external_rate_limit(monkeypatch):
    import ingestion.runners.run_api_partial_sources_audit as mod
    monkeypatch.setattr(mod, "gate_check", lambda sid, q="": "cooldown_skip")
    monkeypatch.setattr(mod, "in_cooldown", lambda sid, q: (True, "2026-06-13T12:00:00Z"))
    t = next(x for x in mod.TARGETS if x["id"] == "federal_register")
    rec = mod.audit_source(t, max_items=3, respect_rate_limit=True)
    assert rec["final_status"] == "NOT_CLOSED_EXTERNAL_RATE_LIMIT"
    assert rec["next_retry_at"] == "2026-06-13T12:00:00Z"
    assert rec["live_called"] is False
