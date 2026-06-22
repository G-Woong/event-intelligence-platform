from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Float, CheckConstraint, DateTime, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class EventCardORM(Base):
    __tablename__ = "event_cards"
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_confidence_score_range",
        ),
        # 마이그레이션 0004 의 ix_event_cards_event_id 와 ORM 정합(드리프트 방지).
        Index("ix_event_cards_event_id", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    theme: Mapped[str] = mapped_column(String, nullable=False)
    impact_path: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="published")
    sectors: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    entities: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    evidence: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    # S1(ADR#16): 카드 = "특정 Event 의 한 스냅샷". NULL = Event 1개짜리 degenerate case(기존 카드 비파괴).
    # use_alter: events.snapshot_card_id ↔ event_cards.event_id 순환 FK 를 create_all 시 ALTER 로
    # 분리(마이그레이션 0004 도 동일하게 별도 create_foreign_key 로 추가). name 은 0004 와 일치.
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL", use_alter=True, name="fk_event_cards_event_id"),
        nullable=True,
    )
