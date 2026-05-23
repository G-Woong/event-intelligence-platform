from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid


class Comment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str
    author: str
    body: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AIReplyRequest(BaseModel):
    event_id: str
    prompt_hint: str = ""
