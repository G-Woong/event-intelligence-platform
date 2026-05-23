from __future__ import annotations

import os
import pytest

RUN_MILVUS = os.getenv("RUN_MILVUS_INTEGRATION") == "1"
skip_milvus = pytest.mark.skipif(not RUN_MILVUS, reason="RUN_MILVUS_INTEGRATION not set")


@skip_milvus
def test_ensure_collection_creates_and_loads():
    from backend.app.db.milvus import connect, ensure_event_embeddings_collection
    from pymilvus import utility
    from backend.app.core.config import settings

    connect()
    col_name = settings.MILVUS_COLLECTION
    # drop for clean test
    if utility.has_collection(col_name):
        from pymilvus import Collection
        Collection(col_name).drop()
    ensure_event_embeddings_collection(dim=1536)
    assert utility.has_collection(col_name)


@skip_milvus
def test_insert_and_search():
    from backend.app.db.milvus import (
        connect,
        ensure_event_embeddings_collection,
        insert_event_embedding,
        search_similar_events,
    )
    from backend.app.services.embedding_client import MockEmbeddingClient

    connect()
    ensure_event_embeddings_collection(dim=1536)

    client = MockEmbeddingClient(dim=1536)
    text = "earthquake in Tokyo 2024"
    vec = client.embed_text(text)
    event_id = "test-evt-001"
    insert_event_embedding(
        event_id=event_id,
        embedding=vec,
        card_id=event_id,
        text_hash="abc123",
        theme="disaster",
    )

    hits = search_similar_events(vec, top_k=5)
    assert len(hits) >= 1
    assert hits[0]["event_id"] == event_id


@skip_milvus
def test_search_excludes_self():
    from backend.app.db.milvus import (
        connect,
        ensure_event_embeddings_collection,
        insert_event_embedding,
        search_similar_events,
    )
    from backend.app.services.embedding_client import MockEmbeddingClient

    connect()
    ensure_event_embeddings_collection(dim=1536)

    client = MockEmbeddingClient(dim=1536)
    vec = client.embed_text("unique test event exclude self")
    event_id = "test-evt-exclude-001"
    insert_event_embedding(event_id=event_id, embedding=vec, card_id=event_id)

    hits = search_similar_events(vec, top_k=5, exclude_event_id=event_id)
    assert all(h["event_id"] != event_id for h in hits)
