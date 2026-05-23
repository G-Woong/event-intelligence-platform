from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.app.models.base import Base


class RawEventORM(Base):
    __tablename__ = "raw_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String(32), nullable=False)
    source_name = Column(String(128), nullable=False)
    external_id = Column(String(512), nullable=True)
    url = Column(String(2048), nullable=False)
    title = Column(String(1024), nullable=True)
    raw_text = Column(Text, nullable=False, default="")
    published_at = Column(DateTime(timezone=True), nullable=True)
    collected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    content_hash = Column(String(64), nullable=False)
    theme_hint = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default="collected")
    enqueued_msg_id = Column(String(64), nullable=True)
    error_reason = Column(String(512), nullable=True)
    event_card_id = Column(UUID(as_uuid=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    raw_metadata = Column(JSONB, nullable=False, server_default="'{}'::jsonb")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
