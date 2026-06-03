from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EventCandidate(BaseModel):
    source_id: str
    url: str
    title: str
    summary: str
    event_type: Optional[str] = None
    entities: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    significance: float = 0.0
    confidence: float = 0.0
    published_at: Optional[str] = None
    extraction_strategy: str = ""
    llm_judged: bool = False
