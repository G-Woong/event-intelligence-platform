"""audit runner 3종(docs/85 Step 4~6) 단위 테스트 — 전부 네트워크 없음.

runner는 run_collection_probe/gate_check 등을 모듈 레벨 import로 보유하므로
runner 모듈 namespace에 monkeypatch한다.
"""
from __future__ import annotations

import json
import os

# 시뮬레이션 모듈의 import 부작용(INGESTION_RATE_LIMIT_BACKEND=local_file setdefault)을
# 기존 기본값(memory)으로 고정 — 다른 테스트의 store backend 오염 방지
os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "memory")

import pytest

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.runners import run_enrichment_live_audit as enrich
from ingestion.runners import run_periodic_collection_simulation as sim
from ingestion.runners import run_primary_seed_live_audit as primary


def _fake_result(source_id: str, raw_path=None, status="LIVE_SUCCESS", items=3):
    return CollectionProbeResult(
        source_id=source_id,
        status=status,
        strategy_used="api",
        items_found=items,
        artifact_paths=ArtifactPaths(raw_payload=str(raw_path) if raw_path else None),
        next_action="integrate_into_pipeline",
    )


def _write_payload(tmp_path, name="payload.json"):
    p = tmp_path / name
    p.write_text(json.dumps({
        "results": [{"title": "Fake item", "url": "https://f.test/1",
                     "description": "desc", "date": "2026-06-13"}]
    }, ensure_ascii=False), encoding="utf-8")
    return p


class _FakeStore:
    def age_seconds(self, key):
        return None


# ── runner (a) primary ───────────────────────────────────────────────────────

def test_primary_runner_outputs_and_cache_skip(tmp_path, monkeypatch):
    payload = _write_payload(tmp_path)
    calls = []

    monkeypatch.setattr(primary, "load_audit_sources", lambda layers=None: [
        {"id": "src_a", "name": "A", "type": "news", "layer": "document_discovery", "status": ""},
        {"id": "src_b", "name": "B", "type": "news", "layer": "document_discovery", "status": ""},
    ])
    monkeypatch.setattr(primary, "gate_check",
                        lambda sid, q="": "cache_skip" if sid == "src_b" else None)
    monkeypatch.setattr(primary, "run_collection_probe",
                        lambda sid, **kw: calls.append(sid) or _fake_result(sid, payload))
    monkeypatch.setattr(primary, "record_call", lambda sid, q="": None)
    monkeypatch.setattr(primary, "get_store", lambda: _FakeStore())
    monkeypatch.setattr(primary, "enforce_min_interval", lambda sid, last: 0.0)
    monkeypatch.setattr(primary, "OUTPUT_JSONL_DIR", tmp_path / "jsonl")
    monkeypatch.setattr(primary, "OUTPUT_REPORTS_DIR", tmp_path / "reports")

    rc = primary.main([])
    assert rc == 0
    assert calls == ["src_a"]  # cache_skip 소스는 네트워크 호출 없음

    jsonl_files = list((tmp_path / "jsonl").glob("primary_seed_live_audit_*.jsonl"))
    md_files = list((tmp_path / "reports").glob("primary_seed_live_audit_*.md"))
    assert len(jsonl_files) == 1 and len(md_files) == 1

    records = [json.loads(l) for l in jsonl_files[0].read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    by_id = {r["source_id"]: r for r in records}
    assert by_id["src_a"]["audit_action"] == "called"
    assert by_id["src_a"]["seed_ready"] == "yes"  # title+url+timestamp+snippet+source_id
    assert by_id["src_b"]["audit_action"] == "cache_skip"
    assert by_id["src_b"]["status"] is None  # skip은 ProbeResult를 만들지 않음


def test_primary_runner_dry_run_no_calls(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(primary, "load_audit_sources", lambda layers=None: [
        {"id": "src_a", "name": "A", "type": "news", "layer": "document_discovery", "status": ""},
    ])
    monkeypatch.setattr(primary, "run_collection_probe",
                        lambda sid, **kw: called.append(sid))
    monkeypatch.setattr(primary, "OUTPUT_JSONL_DIR", tmp_path / "jsonl")
    monkeypatch.setattr(primary, "OUTPUT_REPORTS_DIR", tmp_path / "reports")
    rc = primary.main(["--dry-run"])
    assert rc == 0
    assert called == []


# ── runner (b) enrichment ────────────────────────────────────────────────────

def test_enrichment_budget_and_language_routing(tmp_path, monkeypatch):
    payload = _write_payload(tmp_path)
    calls: list[tuple] = []

    def fake_probe(sid, query=None, max_items=3, **kw):
        calls.append((sid, query))
        return _fake_result(sid, payload)

    monkeypatch.setattr(enrich, "run_collection_probe", fake_probe)
    monkeypatch.setattr(enrich, "gate_check", lambda sid, q="": None)
    monkeypatch.setattr(enrich, "record_call", lambda sid, q="": None)
    monkeypatch.setattr(enrich, "enforce_min_interval", lambda sid, last: 0.0)
    monkeypatch.setattr(enrich, "OUTPUT_JSONL_DIR", tmp_path / "jsonl")
    monkeypatch.setattr(enrich, "OUTPUT_REPORTS_DIR", tmp_path / "reports")

    rc = enrich.main(["--sources", "serper", "gnews",
                      "--queries", "alpha launch event"])
    assert rc == 0
    serper_calls = [q for sid, q in calls if sid == "serper"]
    gnews_calls = [q for sid, q in calls if sid == "gnews"]
    assert len(serper_calls) <= 4  # budget 절단
    assert len(gnews_calls) <= 2
    # gnews는 en 전용 — 한글 대분류가 배정되지 않아야 함
    import re
    assert all(not re.search(r"[가-힣]", q) for q in gnews_calls)


def test_enrichment_query_unsupported_branch(tmp_path, monkeypatch):
    payload = _write_payload(tmp_path)
    monkeypatch.setattr(enrich, "run_collection_probe",
                        lambda sid, query=None, max_items=3, **kw: _fake_result(sid, payload))
    monkeypatch.setattr(enrich, "gate_check", lambda sid, q="": None)
    monkeypatch.setattr(enrich, "record_call", lambda sid, q="": None)
    monkeypatch.setattr(enrich, "enforce_min_interval", lambda sid, last: 0.0)
    monkeypatch.setattr(enrich, "OUTPUT_JSONL_DIR", tmp_path / "jsonl")
    monkeypatch.setattr(enrich, "OUTPUT_REPORTS_DIR", tmp_path / "reports")

    rc = enrich.main([])  # --sources 미지정 → 미지원 소스 참조 record 포함
    assert rc == 0
    jsonl = list((tmp_path / "jsonl").glob("enrichment_live_audit_*.jsonl"))[0]
    records = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines()]
    unsupported = [r for r in records if r["audit_action"] == "query_unsupported"]
    assert {r["source_id"] for r in unsupported} >= {"kofic", "kma", "finnhub", "signal_bz"}
    assert all(r["query"] is None for r in unsupported)
    usages = {r["source_id"]: r["recommended_usage"] for r in unsupported}
    assert usages["kofic"] == "parameterized_lookup_for_verification"
    assert usages["signal_bz"] == "periodic_seed_only"


def test_enrichment_derive_hot_queries_filters_junk(tmp_path):
    primary_jsonl = tmp_path / "primary.jsonl"
    rows = [
        {"source_id": "signal_bz", "layer": "fast_signal",
         "samples": [{"title": "1 이재명 대통령 멜로니"}]},
        {"source_id": "loword", "layer": "fast_signal",
         "samples": [{"title": "키워드 검색량 조회, 분석 - 로워드"}]},  # junk
        {"source_id": "yna", "layer": "document_discovery",
         "samples": [{"title": "일론 머스크, 세계 최초 '조만장자' 등극"}]},
        {"source_id": "kma", "layer": "domain_signal",
         "samples": [{"title": "PTY"}]},  # 코드형 junk
        {"source_id": "kofic", "layer": "domain_signal",
         "samples": [{"title": "군체"}]},
    ]
    primary_jsonl.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    hot = enrich.derive_hot_queries(primary_jsonl)
    queries = [h["query"] for h in hot]
    assert any("이재명" in q for q in queries)
    assert any(q == "군체" for q in queries)
    assert all("로워드" not in q for q in queries)
    assert "PTY" not in queries


# ── runner (c) simulation ────────────────────────────────────────────────────

def test_simulation_cycles_and_cache_skip(tmp_path, monkeypatch):
    payload = _write_payload(tmp_path)
    gate_calls: dict[str, int] = {}

    def fake_gate(sid, q=""):
        gate_calls[sid] = gate_calls.get(sid, 0) + 1
        return "cache_skip" if gate_calls[sid] > 1 else None  # 2번째 cycle부터 cache hit

    state_file = tmp_path / "rate_limit_cache.json"
    state_file.write_text(json.dumps({
        "calls": {"s1:": {"epoch": 1}, "s2:": {"epoch": 1}}, "next_retry": {},
    }), encoding="utf-8")

    monkeypatch.setattr(sim, "gate_check", fake_gate)
    monkeypatch.setattr(sim, "run_collection_probe",
                        lambda sid, **kw: _fake_result(sid, payload))
    monkeypatch.setattr(sim, "record_call", lambda sid, q="": None)
    monkeypatch.setattr(sim, "enforce_min_interval", lambda sid, last: 0.0)
    monkeypatch.setattr(sim, "_artifact_count", lambda sid: 7)  # 호출 전후 동일 → new 0
    monkeypatch.setattr(sim, "_health_state", lambda sid: "HEALTHY")
    monkeypatch.setattr(sim, "_STATE_FILE", state_file)
    monkeypatch.setattr(sim, "OUTPUT_JSONL_DIR", tmp_path / "jsonl")
    monkeypatch.setattr(sim, "OUTPUT_REPORTS_DIR", tmp_path / "reports")

    rc = sim.main(["--sources", "s1", "s2", "--cycles", "2", "--sleep-seconds", "0"])
    assert rc == 0

    jsonl = list((tmp_path / "jsonl").glob("periodic_collection_simulation_*.jsonl"))[0]
    records = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 4  # 2 cycle × 2 source
    cycle1 = [r for r in records if r["cycle"] == 1]
    cycle2 = [r for r in records if r["cycle"] == 2]
    assert all(r["audit_action"] == "called" for r in cycle1)
    assert all(r["audit_action"] == "cache_skip" for r in cycle2)
    assert all(r["artifacts_new"] == 0 for r in cycle2)

    md = list((tmp_path / "reports").glob("periodic_collection_simulation_*.md"))[0]
    content = md.read_text(encoding="utf-8")
    assert "1_cache_skip_no_duplicate_artifacts**: PASS" in content
    assert "3_rate_limit_cache_persisted**: PASS" in content


def test_simulation_verify_rate_limited_followup():
    records = [
        {"cycle": 1, "source_id": "g", "audit_action": "called",
         "status": "RATE_LIMITED", "artifacts_new": 0, "next_action": "retry"},
        {"cycle": 2, "source_id": "g", "audit_action": "cooldown_skip",
         "status": None, "artifacts_new": 0, "next_action": "skipped"},
    ]
    checks = sim.verify_simulation(records, ["g"])
    assert checks["2_rate_limited_skipped_next_cycle"]["result"] == "PASS"
    assert checks["5_failed_sources_have_next_action"]["result"] == "PASS"


def test_simulation_cycles_clamped_to_three(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "gate_check", lambda sid, q="": "cache_skip")
    monkeypatch.setattr(sim, "_health_state", lambda sid: None)
    monkeypatch.setattr(sim, "OUTPUT_JSONL_DIR", tmp_path / "jsonl")
    monkeypatch.setattr(sim, "OUTPUT_REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(sim, "_STATE_FILE", tmp_path / "none.json")
    rc = sim.main(["--sources", "s1", "--cycles", "9", "--sleep-seconds", "0"])
    assert rc == 0
    jsonl = list((tmp_path / "jsonl").glob("*.jsonl"))[0]
    records = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines()]
    assert max(r["cycle"] for r in records) == 3  # 최대 3 cycle 강제
