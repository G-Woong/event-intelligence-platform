from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RawDocument(BaseModel):
    source_id: str
    url: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    status_code: int
    html: str
    strategy: str
    elapsed_sec: float
    content_length: int
    headers: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
