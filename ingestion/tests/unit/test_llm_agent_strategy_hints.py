"""G-4: StrategyMemory llm_agent_hints round-trip + SourceSupervisor unsafe 전략 거부."""
from __future__ import annotations

from ingestion.orchestration.source_strategy_memory import (
    SourceStrategyMemory,
    _to_plain,
    load_strategy_memory,
    save_strategy_memory,
)
from ingestion.orchestration.source_supervisor import decide


def test_llm_agent_hints_round_trip(tmp_path):
    m = SourceStrategyMemory(
        source_id="gdelt", previous_status="EXTERNAL_RATE_LIMITED",
        final_status="EXTERNAL_RATE_LIMITED_PENDING_RESUME",
        llm_agent_hints=("never_disable_on_single_429", "use_host_level_rate_limit"))
    p = tmp_path / "mem.yaml"
    save_strategy_memory([m], p)
    loaded = load_strategy_memory(p)
    assert loaded["gdelt"].llm_agent_hints == (
        "never_disable_on_single_429", "use_host_level_rate_limit")


def test_empty_hints_omitted_from_yaml():
    # 힌트 없는 entry는 llm_agent_hints 키를 직렬화하지 않는다(기존 entry diff noise 방지).
    m = SourceStrategyMemory(source_id="x", previous_status="A", final_status="B")
    assert "llm_agent_hints" not in _to_plain(m)


def test_supervisor_rejects_unsafe_llm_proposal():
    # LLM이 우회(proxy_rotation) 전략을 제안해도 allowed 밖이면 채택하지 않는다.
    d = decide(source_id="gdelt", observed_failure="429 rate limited",
               blocking_layer="RATE_LIMIT",
               llm_propose=lambda failure, allowed: "proxy_rotation", llm_available=True)
    assert d.selected_strategy != "proxy_rotation"
    assert d.selected_strategy in d.allowed_strategies
    assert "proxy_rotation" in d.rejected_unsafe_strategies


def test_supervisor_accepts_allowed_llm_proposal():
    d = decide(source_id="gdelt", observed_failure="429 rate limited",
               blocking_layer="RATE_LIMIT",
               llm_propose=lambda failure, allowed: "query_simplification_spaced_probe",
               llm_available=True)
    assert d.selected_strategy == "query_simplification_spaced_probe"
