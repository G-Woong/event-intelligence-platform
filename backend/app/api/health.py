from __future__ import annotations

from fastapi import APIRouter

from backend.app.db import milvus as milvus_db
from backend.app.db import opensearch as opensearch_db
from backend.app.db import postgres as postgres_db
from backend.app.db import redis as redis_db

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    redis_status = "ok" if redis_db.ping() else "error"
    milvus_status = "ok" if milvus_db.is_connected() else "error"
    postgres_status = "ok" if await postgres_db.ping() else "error"
    opensearch_status = "ok" if opensearch_db.ping() else "error"
    return {
        "status": "ok",
        "version": "0.1.0",
        "components": {
            "redis": redis_status,
            "milvus": milvus_status,
            "postgres": postgres_status,
            "opensearch": opensearch_status,
        },
        "redis": redis_status,
        "milvus": milvus_status,
        "postgres": postgres_status,
    }
