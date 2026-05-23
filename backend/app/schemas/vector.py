from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class SimilarEventQuery(BaseModel):
    query_text: str
    top_k: int = Field(default=5, ge=1, le=50)
    exclude_event_id: Optional[str] = None


class SimilarEventHit(BaseModel):
    event_id: str
    card_id: str
    score: float
    title: str
    summary: str
    theme: str


class SimilarEventResponse(BaseModel):
    hits: list[SimilarEventHit]
