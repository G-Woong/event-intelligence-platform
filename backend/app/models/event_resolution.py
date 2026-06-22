"""Event Resolution 라우팅 토대 ORM (S2a, ADR#16 / EVENT_SCHEMA Part 2 §cluster_event_map·event_links).

cross_source_dedup 클러스터를 영속 Event로 라우팅(event_resolver, S2c)할 때 쓰는 2테이블:
  - cluster_event_map: cluster_id → event_id 라우팅 **단일 진실원천**(event_cards.event_id는 derived).
    재실행 시 같은 cluster가 같은 Event로 가도록 영속.
  - event_links: event ↔ event 링크. 약신호는 status='possible'로 보류(자동병합 금지, reason 기록)
    → 사람/추가신호로 confirmed/rejected/merged 확정(가역성).

S1(event_timeline)에서 이월된 테이블. merge_score entity·domain 축 / heat 4신호는 S4·S2.5로 추가 이월.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base

# event_links.status 허용값(자동병합 금지 — possible 보류가 기본).
LINK_STATUSES = ("possible", "confirmed", "rejected", "merged")


class ClusterEventMapORM(Base):
    """cluster_id → event_id 라우팅 영속화(단일 진실원천). EVENT_SCHEMA Part 2 §cluster_event_map."""

    __tablename__ = "cluster_event_map"
    __table_args__ = (
        Index("ix_cluster_event_map_event_id", "event_id"),
    )

    cluster_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    # RESTRICT(0006, ADR#20): 라우팅 매핑이 가리키는 Event 는 DB 레벨에서 삭제 차단(감사 보호).
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EventLinkORM(Base):
    """event ↔ event 링크. EVENT_SCHEMA Part 2 §event_links. 약신호 자동병합 금지(possible 보류)."""

    __tablename__ = "event_links"
    __table_args__ = (
        CheckConstraint(
            "status IN ('possible', 'confirmed', 'rejected', 'merged')",
            name="ck_event_links_status",
        ),
        Index("ix_event_links_event_id", "event_id"),
        Index("ix_event_links_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # RESTRICT(0006, ADR#20): 링크가 가리키는 Event 는 DB 레벨에서 삭제 차단(possible/merged 이력 보호).
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    linked_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="possible")
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
