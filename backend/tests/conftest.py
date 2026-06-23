from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _force_mock_providers(monkeypatch):
    """Pin the global settings singleton to mock LLM+embedding providers for the
    **backend** suite and drop any cached LLM/embedding client around each test.

    Keeps the default (non-smoke) backend test path deterministic and network-0,
    independent of the developer's local .env: a re-introduced
    EMBEDDING_PROVIDER=openai / LLM_PROVIDER=openai can no longer pull a real
    OpenAI client into the deterministic suite — the singleton instantiation
    that made test_get_embedding_client_singleton depend on .env. (CLAUDE.md:
    tests read STRUCTURE from .env.example; real secrets live only in the
    gitignored .env. The Event/timeline path is network-0.)

    Resets BOTH singleton caches (embedding *and* llm) symmetrically — each has
    its own module-global `_client_cache`, so pinning settings without dropping
    the llm cache would leave a previously-cached real client in place.

    Patches the SINGLETON, not os.environ, so the env-contract tests that build
    their own Settings(...) instances (e.g. test_config_env_contract) are
    unaffected. Tests that exercise the openai branch pass provider= explicitly
    (create_llm_client(provider="openai")) and bypass settings, so they keep
    working. Real OpenAI smoke tests stay gated behind RUN_OPENAI_EMBED_SMOKE.

    Scope: this conftest lives under backend/tests, so it governs the backend
    suite only. ingestion selects its provider via os.getenv("LLM_PROVIDER",
    "mock") (default mock), independent of this settings singleton.
    """
    from backend.app.core.config import settings
    from backend.app.services.embedding_client import reset_embedding_client_cache
    from backend.app.services.llm_client import reset_llm_client_cache

    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock", raising=False)
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "mock", raising=False)
    reset_embedding_client_cache()
    reset_llm_client_cache()
    yield
    reset_embedding_client_cache()
    reset_llm_client_cache()
