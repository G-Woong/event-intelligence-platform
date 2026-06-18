from __future__ import annotations

from datetime import datetime

from backend.app.services.llm_client import reset_llm_client_cache, MockLLMClient
from backend.app.schemas.events import RawEvent
from agents.graphs.event_processing_graph import run


def setup_function():
    reset_llm_client_cache()


def teardown_function():
    reset_llm_client_cache()


def test_full_pipeline_mock():
    import backend.app.services.llm_client as llm_mod
    llm_mod._client_cache = MockLLMClient()

    raw = RawEvent(
        source="test-pipeline",
        url="https://www.reuters.com/test",
        fetched_at=datetime.utcnow(),
        raw_text="Test pipeline event: major developments in geopolitical landscape affecting energy markets.",
        raw_metadata={},
    )

    card = run(raw)

    assert card is not None
    assert card.status == "published"
    assert card.summary
    assert card.title
