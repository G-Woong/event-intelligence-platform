"""E-3: SourceStrategyMemory 저장/로드 + StrategyRouter consume — network 0."""
from __future__ import annotations

from ingestion.orchestration.source_strategy_memory import (
    SourceStrategyMemory,
    is_known_dead_end,
    load_strategy_memory,
    preferred_strategy_for,
    save_strategy_memory,
)
from ingestion.orchestration.strategy_router import (
    decide_strategy,
    decide_strategy_with_memory,
)


def _mem():
    return [
        SourceStrategyMemory(source_id="tmdb", previous_status="NEEDS_PARSER_UNRESOLVED",
                             final_status="OFFICIAL_RECORD_ALIVE",
                             successful_strategy="adapter:tmdb", adapter_name="adapter:tmdb"),
        SourceStrategyMemory(source_id="nyt", previous_status="NEEDS_BODY_FETCH_UNRESOLVED",
                             final_status="PAYWALL_BLOCKED_NO_BYPASS",
                             failed_strategies=("body_ladder:PAYWALL",),
                             preferred_next_strategy="no_bypass_keep_blocked"),
    ]


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "mem.yaml"
    save_strategy_memory(_mem(), path, run_id="R1")
    loaded = load_strategy_memory(path)
    assert set(loaded.keys()) == {"tmdb", "nyt"}
    assert loaded["tmdb"].successful_strategy == "adapter:tmdb"
    assert loaded["nyt"].failed_strategies == ("body_ladder:PAYWALL",)


def test_load_missing_file_returns_empty(tmp_path):
    assert load_strategy_memory(tmp_path / "none.yaml") == {}


def test_no_secret_values_in_yaml(tmp_path):
    path = tmp_path / "mem.yaml"
    save_strategy_memory(_mem(), path, run_id="R1")
    text = path.read_text(encoding="utf-8").lower()
    for forbidden in ("api_key", "apikey", "secret", "authorization", "bearer"):
        assert forbidden not in text


def test_preferred_strategy_prefers_successful():
    m = {x.source_id: x for x in _mem()}
    assert preferred_strategy_for("tmdb", m) == "adapter:tmdb"
    assert preferred_strategy_for("nyt", m) == "no_bypass_keep_blocked"
    assert preferred_strategy_for("absent", m) is None


def test_is_known_dead_end():
    m = {x.source_id: x for x in _mem()}
    assert is_known_dead_end("nyt", m) is True       # terminal, no successful strategy
    assert is_known_dead_end("tmdb", m) is False     # data-alive
    assert is_known_dead_end("absent", m) is False


def test_router_consumes_memory_overrides_preferred_strategy():
    from ingestion.orchestration.source_profile import load_source_profiles
    profiles = {p.source_id: p for p in load_source_profiles()}
    prof = profiles.get("tmdb")
    assert prof is not None
    m = {x.source_id: x for x in _mem()}
    base = decide_strategy(prof)
    learned = decide_strategy_with_memory(prof, m)
    assert learned.preferred_strategy == "adapter:tmdb"
    # 메모리 없으면 base와 동일(하위 호환)
    assert decide_strategy_with_memory(prof, None).preferred_strategy == base.preferred_strategy
