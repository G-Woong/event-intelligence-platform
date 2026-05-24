from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_client = None
_connected = False


def get_client():
    global _client
    if _client is None:
        from opensearchpy import OpenSearch
        from backend.app.core.config import settings
        _client = OpenSearch(
            hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
            use_ssl=False,
            verify_certs=False,
            http_compress=True,
        )
    return _client


def connect() -> bool:
    global _connected
    try:
        client = get_client()
        client.ping()
        _connected = True
        from backend.app.core.config import settings
        logger.info("OpenSearch connected: host=%s port=%s", settings.OPENSEARCH_HOST, settings.OPENSEARCH_PORT)
        return True
    except Exception as exc:
        logger.warning("OpenSearch connect failed: %s", exc)
        _connected = False
        return False


def ping() -> bool:
    try:
        return get_client().ping()
    except Exception:
        return False


def is_connected() -> bool:
    return _connected
