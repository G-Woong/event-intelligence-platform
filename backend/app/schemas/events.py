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


class Event(BaseModel):
    """Event 타임라인 토대 — 안정 주제(사건). EVENT_SCHEMA Part 2 §Event / SPEC §1.4.

    카드(FinalEventCard)는 이 Event 의 '현재 스냅샷 뷰'. cluster_event_map/event_links 는 S2.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    canonical_title: str
    status: Literal["active", "dormant", "closed"] = "active"
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_update_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    heat: float = 0.0
    domains: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    primary_entity_ids: list[str] = Field(default_factory=list)
    snapshot_card_id: Optional[str] = None


class EventUpdate(BaseModel):
    """append-only 변화분. EVENT_SCHEMA Part 2 §EventUpdate / SPEC §1.4.

    evidence 는 §8 EvidenceNode 구조화 이전까지 자유 JSONB(list[dict]) 로 둔다(S8 에서 승격).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str
    observed_at: datetime
    delta_summary: str
    evidence: list[dict] = Field(default_factory=list)
    added_domains: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    heat_delta: float = 0.0


class EventSearchHit(BaseModel):
    card_id: str
    id: str
    title: str
    summary: str | None = None
    theme: str | None = None
    sectors: list[str] = []
    status: str | None = None
    score: float
    confidence_score: float | None = None
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
