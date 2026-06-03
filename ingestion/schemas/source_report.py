from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SourceReport(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    evidence_level: str
    phase: int
    run_at: datetime = Field(default_factory=datetime.utcnow)
    status: str
    quality_score: float
    attempts: int
    strategy_used: Optional[str]
    urls_crawled: int
    articles_extracted: int
    event_candidates_found: int
    errors: list[dict] = Field(default_factory=list)
    known_blockers_hit: list[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    notes: Optional[str] = None
