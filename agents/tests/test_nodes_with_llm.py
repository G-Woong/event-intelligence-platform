from __future__ import annotations

import pytest
from datetime import datetime

from backend.app.services.llm_client import reset_llm_client_cache, MockLLMClient
from backend.app.schemas.events import RawEvent, NormalizedEvent
from agents.nodes.impact_analysis import impact_analysis
from agents.nodes.fact_check import fact_check
from agents.nodes.final_writer import final_card_writer


def _make_normalized() -> NormalizedEvent:
    return NormalizedEvent(
        source="test",
        title="Test Event Title",
        body="Test event body text with relevant details.",
        occurred_at=datetime.utcnow(),
        hash="testhash123",
    )


def setup_function():
    reset_llm_client_cache()


def teardown_function():
    reset_llm_client_cache()


def _inject_mock():
    import backend.app.services.llm_client as llm_mod
    llm_mod._client_cache = MockLLMClient()


def test_impact_analysis_node_mock():
    _inject_mock()
    state = {
        "normalized": _make_normalized(),
        "theme": "geopolitics",
        "sectors": ["energy"],
        "llm_errors": [],
    }
    result = impact_analysis(state)
    assert "impact" in result
    assert result["impact"]
    assert "[skip]" not in result["impact"]


def test_fact_check_node_mock():
    _inject_mock()
    state = {
        "normalized": _make_normalized(),
        "evidence": ["[mock-evidence]"],
        "llm_errors": [],
    }
    result = fact_check(state)
    assert result["fact_check"] in ("pass", "hold")


def test_final_writer_node_mock():
    _inject_mock()
    state = {
        "normalized": _make_normalized(),
        "theme": "geopolitics",
        "sectors": ["energy"],
        "entities": ["EntityA"],
        "impact": "[mock] medium-term supply disruption risk",
        "evidence": [],
        "llm_errors": [],
    }
    result = final_card_writer(state)
    assert result.get("final_card") is not None
    card = result["final_card"]
    assert card.summary
    assert card.title == "Test Event Title"


def test_node_llm_failure_fallback(monkeypatch):
    import backend.app.services.llm_client as llm_mod

    class BrokenClient(MockLLMClient):
        def complete_json(self, prompt, *, schema, **kwargs):
            raise RuntimeError("simulated LLM failure")

    llm_mod._client_cache = BrokenClient()
    state = {
        "normalized": _make_normalized(),
        "theme": "geopolitics",
        "sectors": ["energy"],
        "llm_errors": [],
    }
    result = impact_analysis(state)
    assert "[fallback]" in result["impact"]
    assert len(result.get("llm_errors", [])) > 0
