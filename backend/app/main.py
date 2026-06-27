from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import (
    admin,
    ai_replies,
    comments,
    events,
    health,
    internal,
    internal_ops,
    sectors,
    themes,
)
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging
from backend.app.core.observability import setup_langsmith
from backend.app.core.security import assert_startup_auth_posture, require_admin_token
from backend.app.db import milvus as milvus_db
from backend.app.db import opensearch as opensearch_db
from backend.app.db import postgres as postgres_db  # noqa: F401
from backend.app.db import redis as redis_db
from backend.app.services import opensearch_index_service

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_langsmith()

    # admin 인증 자세 강제(prod fail-closed) + APP_ENV=dev 오배포 경고. 단일 출처: security.py.
    assert_startup_auth_posture()

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
# ADR#72 internal ops dashboard read-only API(reviewer pipeline workflow state·public truth 아님).
# 이중 게이트: admin-token(아래 dependency·prod fail-closed) + INTERNAL_OPS_DASHBOARD_ENABLED flag(기본 off→404).
app.include_router(internal_ops.router, prefix="/api/internal/ops", dependencies=[Depends(require_admin_token)])
