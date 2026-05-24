from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.logging import configure_logging
from backend.app.core.observability import setup_langsmith
from backend.app.core.security import require_admin_token
from backend.app.db import redis as redis_db, milvus as milvus_db, postgres as postgres_db, opensearch as opensearch_db  # noqa: F401
from backend.app.services import opensearch_index_service
from backend.app.api import health, events, themes, sectors, comments, ai_replies, admin, internal

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_langsmith()

    if not settings.ADMIN_API_TOKEN:
        logger.warning("ADMIN_API_TOKEN unset — admin endpoints unauthenticated (dev only)")

    if redis_db.ping():
        logger.info("Redis: connected")
    else:
        logger.warning("Redis: not reachable at startup")

    if milvus_db.connect():
        logger.info("Milvus: connected")
    else:
        logger.warning("Milvus: not reachable at startup (non-fatal)")

    try:
        if opensearch_db.connect():
            opensearch_index_service.ensure_event_cards_index()
            logger.info("OpenSearch: connected and index ensured")
        else:
            logger.warning("OpenSearch: not reachable at startup (non-fatal)")
    except Exception as exc:
        logger.warning("OpenSearch startup error: %s", exc)

    yield


app = FastAPI(title="Event Intelligence API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token", "Accept"],
    max_age=600,
)

app.include_router(health.router)
app.include_router(events.router)
app.include_router(themes.router)
app.include_router(sectors.router)
app.include_router(comments.router)
app.include_router(ai_replies.router)
app.include_router(admin.router, dependencies=[Depends(require_admin_token)])
app.include_router(internal.router, prefix="/api/internal", dependencies=[Depends(require_admin_token)])
