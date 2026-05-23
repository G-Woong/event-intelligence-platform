from __future__ import annotations

import logging

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
    return _connected


def ensure_collection(name: str, dim: int = 768) -> None:
    pass


def insert_embedding(collection: str, event_id: str, vector: list[float]) -> None:
    pass


def search_similar_events(collection: str, vector: list[float], top_k: int = 5) -> list[dict]:
    return []
