from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.postgres import get_session
from backend.app.schemas.comments import Comment
from backend.app.services import comment_service

router = APIRouter(prefix="/api", tags=["comments"])


@router.post("/comments", response_model=Comment)
async def add_comment(comment: Comment, session: AsyncSession = Depends(get_session)):
    return await comment_service.add_comment(session, comment)


@router.get("/events/{event_id}/comments", response_model=list[Comment])
async def list_comments(event_id: str, session: AsyncSession = Depends(get_session)):
    return await comment_service.list_by_event(session, event_id)
