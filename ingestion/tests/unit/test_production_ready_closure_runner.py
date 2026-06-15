"""G-10/11/12: closure runner 통합 — 비-ready source 승격/disable, non_excluded_not_ready=0.

네트워크 0: vendor_fetch/body_rescue/gdelt_probe 주입. canonical config는 temp 복사본 사용.
"""
from __future__ import annotations

import yaml

from ingestion.orchestration.source_strategy_memory import SourceStrategyMemory, save_strategy_memory
from ingestion.orchestration.vendor_api_routes import VendorRouteResult
from ingestion.orchestration.full_source_revival import build_eventqueue_record
from ingestion.tools.run_source_readiness_closure import run_source_readiness_closure


def _write_profiles(path, profiles: dict):
    path.write_text(yaml.safe_dump({"version": 2, "profiles": profiles}, allow_unicode=True),
                    encoding="utf-8")


def _eq(sid, rt, sig):
    return build_eventqueue_record(record_type=rt, source_id=sid, title_or_label=f"{sid} x",
        source_url_or_evidence=f"https://{sid}.test/1", canonical_url=f"https://{sid}.test/1",
        published_at_or_observed_at="2026-06-15T00:00:00Z", body_state_or_signal=sig,
        confirmation_policy="evidence_required", quality_pre_gate_decision="pass")


def _vendor_ok(sid):
    return VendorRouteResult(sid, "route", True, 200, "structured_signal",
                             (_eq(sid, "structured_signal", "economic_indicator"),), None, 1)


def _paths(tmp_path):
    return dict(
        state_path=tmp_path / "state.json", queue_path=tmp_path / "q.jsonl",
        raw_mirror_path=tmp_path / "raw.jsonl", dedup_index_path=tmp_path / "dedup.json",
        monitoring_dir=tmp_path / "mon", output_dir=tmp_path / "out")


def _setup_configs(tmp_path):
    prof_path = tmp_path / "profiles.yaml"
    mem_path = tmp_path / "memory.yaml"
    _write_profiles(prof_path, {
        "bbc": {"enabled": True, "source_group": "news", "purpose": "news",
                "live_eligible": "true", "requires_api_key": False, "min_interval_seconds": 1800},
        "bok_ecos": {"enabled": True, "source_group": "official", "purpose": "regulatory",
                     "requires_api_key": True, "live_eligible": "false", "skip_reason": "requires_api_key",
                     "min_interval_seconds": 1800},
        "its": {"enabled": False, "source_group": "domain", "purpose": "domain",
                "live_eligible": "false", "skip_reason": "not_service_useful", "min_interval_seconds": 1800},
    })
    save_strategy_memory([
        SourceStrategyMemory(source_id="bok_ecos", previous_status="NEEDS_PARSER_UNRESOLVED",
                             final_status="REQUIRES_VENDOR_SPECIFIC_API_CONTRACT"),
    ], mem_path, run_id="t0")
    return prof_path, mem_path


def test_closure_promotes_vendor_source(tmp_path):
    prof, mem = _setup_configs(tmp_path)
    r = run_source_readiness_closure(
        profiles_path=prof, memory_path=mem,
        vendor_fetch=_vendor_ok, body_rescue=lambda s: (False, [], None, "n/a"),
        gdelt_probe=lambda s: (False, [], None),
        apply_config=True, write_outputs=True, now=None, **_paths(tmp_path))
    assert "bok_ecos" in r["promoted"]
    assert r["non_excluded_not_ready"] == 0
    assert r["raw_events_written"] >= 1
    assert r["bridge_contract_pass"] is True
    assert r["critical_alerts"] == 0


def test_closure_no_targets_when_all_ready(tmp_path):
    # bbc ready, its excluded, bok_ecos already alive via memory
    prof = tmp_path / "p.yaml"
    mem = tmp_path / "m.yaml"
    _write_profiles(prof, {
        "bbc": {"enabled": True, "source_group": "news", "purpose": "news",
                "live_eligible": "true", "requires_api_key": False, "min_interval_seconds": 1800}})
    save_strategy_memory([], mem, run_id="t0")
    r = run_source_readiness_closure(
        profiles_path=prof, memory_path=mem, vendor_fetch=lambda s: None,
        body_rescue=lambda s: (False, [], None, ""), gdelt_probe=lambda s: (False, [], None),
        apply_config=False, write_outputs=False, **_paths(tmp_path))
    assert r["non_excluded_not_ready"] == 0
    assert r["gap_summary"]["targets"] == 0


def test_real_configs_honest_holdovers_only():
    # 실제(Phase G 적용) config: 정직하게 unknown/source_without_state/critical=0이고,
    # 남은 non-ready는 문서화된 홀드오버(gdelt rate-limit + culture_info/product_hunt degraded)뿐.
    r = run_source_readiness_closure(
        vendor_fetch=lambda s: None, body_rescue=lambda s: (False, [], None, ""),
        gdelt_probe=lambda s: (False, [], None),
        apply_config=False, write_outputs=False)
    assert r["unknown"] == 0 and r["source_without_state"] == 0
    assert r["critical_alerts"] == 0
    # non-ready는 known 홀드오버의 부분집합(과대 평가/은폐 금지).
    # Phase G-2: dcinside는 robots-allowed static fetch로 실데이터 수집하나 list-preview-only +
    # AI-차단/ToS 미검증 caveat로 DEGRADED(적대 리뷰 흡수) → 4번째 정직한 홀드오버.
    holdovers = {g.source_id for g in r["gaps"]}
    assert holdovers.issubset({"gdelt", "culture_info", "product_hunt", "dcinside"})
    assert r["non_excluded_not_ready"] <= 4


def test_disabled_sources_are_excluded_in_profiles():
    from ingestion.orchestration.source_profile import load_source_profiles
    profiles = {p.source_id: p for p in load_source_profiles("ingestion/configs/source_profiles.yaml")}
    # its/google_trends_explore는 여전히 disabled. dcinside는 Phase G-2에서 robots 허용 갤러리
    # static fetch로 복구되어 active(아래에서 별도 확인).
    for sid in ("its", "google_trends_explore"):
        assert profiles[sid].enabled is False, f"{sid} should be disabled"
    assert profiles["dcinside"].enabled is True  # Phase G-2: robots-allowed static fetch, no bypass
