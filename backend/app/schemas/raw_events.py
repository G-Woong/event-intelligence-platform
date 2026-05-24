from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RawEventCreate(BaseModel):
    source_type: str = "rss"
    source_name: str
    external_id: Optional[str] = None
    url: str
    title: Optional[str] = None
    raw_text: str = ""
    published_at: Optional[datetime] = None
    content_hash: str
    theme_hint: Optional[str] = None
    raw_metadata: dict = Field(default_factory=dict)


class RawEventRecord(BaseModel):
    id: str
    source_type: str
    source_name: str
    external_id: Optional[str]
    url: str
    title: Optional[str]
    raw_text: str
    published_at: Optional[datetime]
    collected_at: datetime
    content_hash: str
    theme_hint: Optional[str]
    status: str
    enqueued_msg_id: Optional[str]
    error_reason: Optional[str]
    event_card_id: Optional[str] = None
    processed_at: Optional[datetime] = None
    raw_metadata: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RawEventCreateResponse(BaseModel):
    record: RawEventRecord
    is_duplicate: bool
    enqueued_msg_id: Optional[str]


class RawEventStatusUpdate(BaseModel):
    status: str
    error_reason: Optional[str] = None
    event_card_id: Optional[str] = None


class ReconcileStuckRequest(BaseModel):
    before_seconds: int = 600
    limit: int = 100
    dry_run: bool = True
    error_reason: str = "reconciler: stuck enqueued"


class ReconcileStuckResponse(BaseModel):
    stuck_count: int
    marked_failed: int
    dry_run: bool
    items: list[RawEventRecord]


class RequeueRequest(BaseModel):
    force: bool = False


class RequeueResponse(BaseModel):
    record: RawEventRecord
    enqueued_msg_id: str
    requeue_count: int
