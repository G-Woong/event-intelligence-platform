from __future__ import annotations

import pytest

from backend.app.services.llm_client import reset_llm_client_cache, MockLLMClient
from agents.tools.llm import analyze_impact, fact_check_claims, write_final_card


def setup_function():
    reset_llm_client_cache()


def teardown_function():
    reset_llm_client_cache()


def test_analyze_impact_mock(monkeypatch):
    import backend.app.services.llm_client as llm_mod
    llm_mod._client_cache = MockLLMClient()
    result = analyze_impact(
        title="Test event",
        body="Something happened in the energy sector.",
        theme="geopolitics",
        sectors=["energy", "defense"],
    )
    assert result.impact
    assert "[mock]" in result.impact or "[fallback]" in result.impact
    assert result.horizon in ("short", "medium", "long")
    assert 0.0 <= result.confidence <= 1.0


def test_fact_check_mock(monkeypatch):
    import backend.app.services.llm_client as llm_mod
    llm_mod._client_cache = MockLLMClient()
    result = fact_check_claims(
        title="Test event",
        body="Claims about the event.",
        evidence=["[mock-evidence-1]"],
    )
    assert result.status in ("pass", "hold")
    assert isinstance(result.reasoning, str)


def test_write_final_card_mock(monkeypatch):
    import backend.app.services.llm_client as llm_mod
    llm_mod._client_cache = MockLLMClient()
    result = write_final_card(state_snapshot={
        "title": "Test Event",
        "body": "Body text for test event.",
        "entities": ["EntityA"],
        "theme": "geopolitics",
        "past_context": [],
    })
    assert result.summary
    assert result.headline
