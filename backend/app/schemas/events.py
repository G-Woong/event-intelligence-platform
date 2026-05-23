from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


class RawEvent(BaseModel):
    source: str
    url: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    raw_text: str
    raw_metadata: dict = Field(default_factory=dict)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)
