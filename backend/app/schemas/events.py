from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


class RawEvent(BaseModel):
    source: str
    url: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    raw_text: str
    raw_metadata: dict = Field(default_factory=dict)
    raw_event_id: Optional[str] = None


class NormalizedEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str
    title: str
    body: str
    occurred_at: datetime
    language: str = "en"
    hash: str


class FinalEventCard(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    summary: str
    theme: str
    sectors: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    impact_path: str = ""
    evidence: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["published", "hold"] = "published"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventSearchHit(BaseModel):
    card_id: str
    title: str
    summary: str | None = None
    theme: str | None = None
    sectors: list[str] = []
    status: str | None = None
    score: float
    created_at: datetime | None = None


class EventSearchResponse(BaseModel):
    total: int
    hits: list[EventSearchHit]


class ReindexRequest(BaseModel):
    limit: int = 1000
    dry_run: bool = False


class ReindexResponse(BaseModel):
    indexed: int
    dry_run: bool
