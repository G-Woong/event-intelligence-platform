"""R-EnvLoadAsymmetry regression — entrypoints load .env so key-required sources
are not falsely reported NEEDS_API when the key actually exists in .env.

run_one_source.run_source() is the shared funnel for run_one_source / run_phase /
run_all_phases; run_production_orchestration.main() loads it explicitly at the CLI
boundary. Values are never read/printed — only present/absent matters.
"""
from __future__ import annotations


def test_run_source_invokes_load_env(monkeypatch):
    # run_source() must call load_env() BEFORE precheck so os.getenv sees .env keys.
    import ingestion.runners.run_one_source as r1s

    calls = []
    monkeypatch.setattr(r1s, "load_env", lambda *a, **k: calls.append(1) or {})
    monkeypatch.setattr(r1s, "configure_ingestion_logging", lambda *a, **k: None)

    class _Stub:
        def precheck_status(self):
            return {"status": "NEEDS_API_KEY", "reason": "stub short-circuit (no network)"}

    monkeypatch.setattr("ingestion.sources._registry.get_source_instance", lambda sid: _Stub())
    # unregistered id → _handle_precheck returns early without writing a report file
    out = r1s.run_source("zzz_unregistered_test_source")
    assert calls, "run_source must invoke load_env() before precheck"
    assert out["status"] == "NEEDS_API_KEY"


def test_keyed_source_precheck_needs_key_when_absent(monkeypatch):
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    from ingestion.core.source_registry import load_registry
    from ingestion.sources.opendart import OpenDARTSource

    spec = load_registry().get("opendart")
    assert OpenDARTSource(spec).precheck_status()["status"] == "NEEDS_API_KEY"


def test_keyed_source_precheck_passes_when_key_present(monkeypatch):
    # simulate the key being present in the environment (as load_env would make it).
    monkeypatch.setenv("OPENDART_API_KEY", "dummy_test_value")  # pragma: allowlist secret
    from ingestion.core.source_registry import load_registry
    from ingestion.sources.opendart import OpenDARTSource

    spec = load_registry().get("opendart")
    assert OpenDARTSource(spec).precheck_status() is None


def test_production_orchestration_main_invokes_load_env(monkeypatch, tmp_path):
    # CLI entrypoint must invoke load_env() (dry-run = no network).
    import ingestion.tools.run_production_orchestration as rpo

    calls = []
    real = rpo.load_env
    monkeypatch.setattr(rpo, "load_env", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    rc = rpo.main([
        "--mode", "production-dry-run",
        "--state-path", str(tmp_path / "s.json"),
        "--event-queue-path", str(tmp_path / "q.jsonl"),
        "--raw-events-mirror", str(tmp_path / "m.jsonl"),
        "--monitoring-dir", str(tmp_path / "mon"),
    ])
    assert calls, "run_production_orchestration.main must invoke load_env()"
    assert rc == 0
