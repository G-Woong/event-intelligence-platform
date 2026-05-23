from __future__ import annotations

import uuid
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.comment import CommentORM
from backend.app.schemas.comments import Comment


def _orm_to_comment(row: CommentORM) -> Comment:
    return Comment(
        id=str(row.id),
        event_id=str(row.event_id),
        author=row.author,
        body=row.body,
        created_at=row.created_at,
    )


async def add_comment(session: AsyncSession, comment: Comment) -> Comment:
    try:
        comment_id = uuid.UUID(comment.id)
    except (ValueError, AttributeError):
        comment_id = uuid.uuid4()
    try:
        event_id = uuid.UUID(comment.event_id)
    except (ValueError, AttributeError):
        event_id = uuid.uuid4()

    created_at = comment.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    row = CommentORM(
        id=comment_id,
        event_id=event_id,
        author=comment.author,
        body=comment.body,
        created_at=created_at,
    )
    session.add(row)
    await session.commit()
    return _orm_to_comment(row)


async def list_by_event(session: AsyncSession, event_id: str) -> list[Comment]:
    try:
        eid = uuid.UUID(event_id)
    except (ValueError, AttributeError):
        return []
    stmt = (
        select(CommentORM)
        .where(CommentORM.event_id == eid)
        .order_by(CommentORM.created_at)
    )
    result = await session.execute(stmt)
    return [_orm_to_comment(row) for row in result.scalars()]
