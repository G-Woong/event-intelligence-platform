from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import settings

_engine: Optional[AsyncEngine] = None
_session_local = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=10,
        )
    return _engine


def _get_session_factory():
    global _session_local
    if _session_local is None:
        _session_local = async_sessionmaker(
            _get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_local


async def get_session():
    async with _get_session_factory()() as session:
        yield session


async def ping() -> bool:
    try:
        async with asyncio.timeout(1.0):
            async with _get_session_factory()() as session:
                await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
