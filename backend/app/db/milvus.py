from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_connected = False


def connect() -> bool:
    global _connected
    try:
        from pymilvus import connections
        from backend.app.core.config import settings
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=str(settings.MILVUS_PORT),
        )
        _connected = True
        logger.info("Milvus connected: host=%s port=%s", settings.MILVUS_HOST, settings.MILVUS_PORT)
        return True
    except Exception as exc:
        logger.warning("Milvus connect failed: %s", exc)
        _connected = False
        return False


def is_connected() -> bool:
    """Lazy ping — falls back to module flag if utility unavailable."""
    try:
        from pymilvus import utility
        utility.get_server_version()
        return True
    except Exception:
        return False


def ensure_event_embeddings_collection(dim: int = 1536) -> None:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        utility,
    )
    from backend.app.core.config import settings
    name = settings.MILVUS_COLLECTION
    if utility.has_collection(name):
        col = Collection(name)
        col.load()
        return
    fields = [
        FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="event_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="card_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="text_hash", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="theme", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="created_at", dtype=DataType.INT64),
        FieldSchema(name="metadata_json", dtype=DataType.VARCHAR, max_length=2048),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(fields=fields, description="event embeddings for RAG")
    col = Collection(name=name, schema=schema)
    col.create_index(
        field_name="embedding",
        index_params={
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 128},
        },
    )
    col.load()
    logger.info("Milvus collection created: %s dim=%d", name, dim)


def insert_event_embedding(
    event_id: str,
    embedding: list[float],
    *,
    card_id: str = "",
    text_hash: str = "",
    theme: str = "",
    source_type: str = "agent",
    metadata_json: str = "{}",
) -> None:
    from pymilvus import Collection
    from backend.app.core.config import settings
    col = Collection(settings.MILVUS_COLLECTION)
    data: list[Any] = [
        [event_id],
        [card_id or event_id],
        [text_hash[:64]],
        [theme[:64]],
        [source_type[:32]],
        [int(time.time())],
        [metadata_json[:2048]],
        [embedding],
    ]
    col.insert(data)
    col.flush()
    logger.debug("Milvus insert ok: event_id=%s", event_id)


def search_similar_events(
    embedding: list[float],
    top_k: int = 5,
    exclude_event_id: str | None = None,
) -> list[dict]:
    from pymilvus import Collection
    from backend.app.core.config import settings
    col = Collection(settings.MILVUS_COLLECTION)
    output_fields = ["event_id", "card_id", "theme", "text_hash"]
    results = col.search(
        data=[embedding],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 8}},
        limit=top_k + (1 if exclude_event_id else 0),
        output_fields=output_fields,
    )
    hits = []
    for hit in results[0]:
        # pymilvus 2.4.x: hit.entity.get(key) takes 1 arg; no default supported
        eid = hit.entity.get("event_id") or ""
        if exclude_event_id and eid == exclude_event_id:
            continue
        hits.append({
            "event_id": eid,
            "card_id": hit.entity.get("card_id") or "",
            "score": hit.score,
            "theme": hit.entity.get("theme") or "",
        })
        if len(hits) >= top_k:
            break
    return hits
