from __future__ import annotations

import os
import pytest

from backend.app.services.embedding_client import (
    MockEmbeddingClient,
    OpenAIEmbeddingClient,
    create_embedding_client,
    reset_embedding_client_cache,
    get_embedding_client,
)


def test_mock_deterministic():
    client = MockEmbeddingClient(dim=1536)
    v1 = client.embed_text("hello world")
    v2 = client.embed_text("hello world")
    assert v1 == v2


def test_mock_different_texts_differ():
    client = MockEmbeddingClient(dim=1536)
    v1 = client.embed_text("event A happened in Tokyo")
    v2 = client.embed_text("completely different text XYZ")
    assert v1 != v2


def test_mock_dim():
    client = MockEmbeddingClient(dim=1536)
    v = client.embed_text("test")
    assert len(v) == 1536


def test_mock_unit_norm():
    client = MockEmbeddingClient(dim=1536)
    v = client.embed_text("norm test")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-4


def test_mock_embed_texts():
    client = MockEmbeddingClient(dim=8)
    texts = ["alpha", "beta", "gamma"]
    vecs = client.embed_texts(texts)
    assert len(vecs) == 3
    assert all(len(v) == 8 for v in vecs)


def test_openai_missing_key_raises():
    env_backup = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="OPENAI_API_KEY is not set"):
            OpenAIEmbeddingClient()
    finally:
        if env_backup is not None:
            os.environ["OPENAI_API_KEY"] = env_backup


def test_openai_missing_key_no_key_in_message():
    """키 값이 에러 메시지에 포함되지 않아야 한다."""
    fake_key = "sk-fake-secret-12345"
    os.environ["OPENAI_API_KEY"] = fake_key
    try:
        client = OpenAIEmbeddingClient()
        # 초기화는 성공 (실 API 호출 안 함)
        assert client is not None
    except Exception as exc:
        assert fake_key not in str(exc), "API key leaked in exception message"
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_create_embedding_client_mock():
    reset_embedding_client_cache()
    client = create_embedding_client(provider="mock")
    assert isinstance(client, MockEmbeddingClient)


def test_get_embedding_client_singleton():
    reset_embedding_client_cache()
    c1 = get_embedding_client()
    c2 = get_embedding_client()
    assert c1 is c2
    reset_embedding_client_cache()


@pytest.mark.skipif(
    not os.getenv("RUN_OPENAI_EMBED_SMOKE"),
    reason="RUN_OPENAI_EMBED_SMOKE not set",
)
def test_openai_smoke():
    client = OpenAIEmbeddingClient()
    v = client.embed_text("test embedding smoke")
    assert len(v) == 1536
    assert all(isinstance(x, float) for x in v)
