from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Float, CheckConstraint, DateTime, func, text
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
