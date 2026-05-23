from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.core.logging import configure_logging
from backend.app.db import redis as redis_db, milvus as milvus_db, postgres as postgres_db  # noqa: F401
from backend.app.api import health, events, themes, sectors, comments, ai_replies, admin

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if redis_db.ping():
        logger.info("Redis: connected")
    else:
        logger.warning("Redis: not reachable at startup")

    if milvus_db.connect():
        logger.info("Milvus: connected")
    else:
        logger.warning("Milvus: not reachable at startup (non-fatal)")

    yield


app = FastAPI(title="Event Intelligence API", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(events.router)
app.include_router(themes.router)
app.include_router(sectors.router)
app.include_router(comments.router)
app.include_router(ai_replies.router)
app.include_router(admin.router)
