from __future__ import annotations

import os
import pytest

from backend.app.services.llm_client import (
    MockLLMClient,
    LLMClient,
    create_llm_client,
    reset_llm_client_cache,
)


def setup_function():
    reset_llm_client_cache()


def teardown_function():
    reset_llm_client_cache()


def test_mock_complete_deterministic():
    client = MockLLMClient()
    r1 = client.complete("describe the impact of the event")
    r2 = client.complete("describe the impact of the event")
    assert r1 == r2
    assert "[mock]" in r1


def test_mock_complete_json_schema():
    from pydantic import BaseModel
    from typing import Literal

    class FactCheckOutput(BaseModel):
        status: Literal["pass", "hold"]
        reasoning: str

    client = MockLLMClient()
    result = client.complete_json("some prompt", schema=FactCheckOutput)
    assert result is not None
    assert result.status == "pass"
    assert isinstance(result.reasoning, str)


def test_create_llm_client_default_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    reset_llm_client_cache()
    client = create_llm_client(provider="mock")
    assert isinstance(client, MockLLMClient)
    reply = client.complete("hello world")
    assert "[mock]" in reply


def test_openai_client_init_without_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ValueError) as exc_info:
        create_llm_client(provider="openai")
    msg = str(exc_info.value)
    assert "len=0" in msg
    assert "sk-" not in msg


def test_legacy_LLMClient_compatibility():
    client = LLMClient(provider="mock")
    reply = client.complete("event_id=test-id hint=summarize")
    assert "[mock]" in reply
