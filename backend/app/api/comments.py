from __future__ import annotations

from fastapi import APIRouter
from backend.app.schemas.comments import Comment
from backend.app.services import comment_service

router = APIRouter(prefix="/api", tags=["comments"])


@router.post("/comments", response_model=Comment)
def add_comment(comment: Comment):
    return comment_service.add_comment(comment)


@router.get("/events/{event_id}/comments", response_model=list[Comment])
def list_comments(event_id: str):
    return comment_service.list_by_event(event_id)
