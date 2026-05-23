from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from backend.app.schemas.events import NormalizedEvent
from agents.nodes.retrieve_context import retrieve_past_context


def _normalized(**kwargs) -> NormalizedEvent:
    defaults = dict(
        source="test",
        title="Earthquake in Tokyo",
        body="A major earthquake struck the Tokyo region today.",
        occurred_at=__import__("datetime").datetime.utcnow(),
        hash="abc123",
    )
    defaults.update(kwargs)
    return NormalizedEvent(**defaults)


def test_retrieve_past_context_no_normalized():
    state = {}
    result = retrieve_past_context(state)
    assert result["past_context"] == []
    assert result["retrieved_context"] == []


def test_retrieve_past_context_populates_both_fields():
    normalized = _normalized()
    fake_hits = [
        {"event_id": "evt-1", "card_id": "evt-1", "score": 0.9, "title": "Prior Quake", "summary": "Smaller quake last month.", "theme": "disaster"},
    ]

    with patch("agents.nodes.retrieve_context.vector_search.search_similar", return_value=fake_hits):
        state = {"normalized": normalized}
        result = retrieve_past_context(state)

    assert len(result["past_context"]) == 1
    assert "Prior Quake" in result["past_context"][0]
    assert result["retrieved_context"] == fake_hits


def test_retrieve_past_context_failure_fallback():
    normalized = _normalized()

    with patch(
        "agents.nodes.retrieve_context.vector_search.search_similar",
        side_effect=ConnectionError("backend down"),
    ):
        state = {"normalized": normalized, "llm_errors": []}
        result = retrieve_past_context(state)

    assert result["past_context"] == ["[fallback-context]"]
    assert result["retrieved_context"] == []
    assert any("retrieve_past_context" in e for e in result["llm_errors"])


def test_retrieve_past_context_appends_to_existing_errors():
    normalized = _normalized()

    with patch(
        "agents.nodes.retrieve_context.vector_search.search_similar",
        side_effect=RuntimeError("timeout"),
    ):
        state = {"normalized": normalized, "llm_errors": ["prior error"]}
        result = retrieve_past_context(state)

    assert len(result["llm_errors"]) == 2
    assert result["llm_errors"][0] == "prior error"


def test_retrieve_passes_exclude_event_id():
    normalized = _normalized()

    with patch("agents.nodes.retrieve_context.vector_search.search_similar", return_value=[]) as mock_search:
        state = {"normalized": normalized}
        retrieve_past_context(state)

    _, kwargs = mock_search.call_args
    assert kwargs.get("exclude_event_id") == normalized.id
