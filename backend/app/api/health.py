from __future__ import annotations

from fastapi import APIRouter
from backend.app.db import redis as redis_db, milvus as milvus_db

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "redis": "ok" if redis_db.ping() else "error",
        "milvus": "ok" if milvus_db.is_connected() else "disconnected",
    }
