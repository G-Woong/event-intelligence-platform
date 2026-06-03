from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExtractionDiagnostics(BaseModel):
    source_id: str
    url: str
    attempt_no: int
    strategy: str
    success: bool
    quality_score: float
    quality_status: str
    body_length: int
    title_present: bool
    published_at_present: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    dom_snapshot_path: Optional[str] = None
    elapsed_sec: float = 0.0
    strategies_tried: list[str] = Field(default_factory=list)
