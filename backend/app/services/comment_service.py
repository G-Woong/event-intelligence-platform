from __future__ import annotations

from backend.app.schemas.comments import Comment

_store: list[Comment] = []


def add_comment(comment: Comment) -> Comment:
    _store.append(comment)
    return comment


def list_by_event(event_id: str) -> list[Comment]:
    return [c for c in _store if c.event_id == event_id]
