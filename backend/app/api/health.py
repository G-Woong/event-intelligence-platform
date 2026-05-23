from __future__ import annotations

from fastapi import APIRouter

from backend.app.db import milvus as milvus_db
from backend.app.db import postgres as postgres_db
from backend.app.db import redis as redis_db

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "redis": "ok" if redis_db.ping() else "error",
        "milvus": "ok" if milvus_db.is_connected() else "error",
        "postgres": "ok" if await postgres_db.ping() else "error",
    }
