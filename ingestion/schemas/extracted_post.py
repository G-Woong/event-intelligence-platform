from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ExtractedPost(BaseModel):
    source_id: str
    url: str
    strategy: str
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    title: Optional[str] = None
    body: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    engagement: dict = Field(default_factory=dict)
    language: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    quality_score: float = 0.0
    quality_status: str = "FAILED"
