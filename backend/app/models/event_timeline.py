"""Event 타임라인 토대 ORM (S1, ADR#16 / EVENT_SCHEMA Part 2).

사건을 1회성 카드 → **진화하는 Event 타임라인 객체**로(ADR#16). 카드(event_cards)는
이 Event의 '현재 스냅샷 뷰'로 재정의된다(비파괴 — event_cards.event_id nullable FK).

S1 스코프(최소 토대): events / event_updates / event_cards.event_id FK 만.
cluster_event_map / event_links 는 라우팅·약신호 링크가 확정되는 S2(Resolution)로 이월.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class EventORM(Base):
    """events 테이블 — 안정 주제(사건). EVENT_SCHEMA Part 2 §Event.

    heat 감쇠로 status(active→dormant→closed) 자동 전이는 S2(Resolution)에서 구동한다.
    snapshot_card_id 는 현재 노출 카드(event_cards.id) — 쌍방향 일관: 그 카드의 event_id 는
    이 Event 를 역참조해야 한다(R-EventModelMigration 불변식).
    """

    __tablename__ = "events"
    __table_args__ = (
        # heat/last_update_at 의 DESC 정렬 조회는 btree 인덱스의 backward scan 으로 충족된다.
        Index("ix_events_heat", "heat"),
        Index("ix_events_status", "status"),
        Index("ix_events_last_update_at", "last_update_at"),
        Index("ix_events_first_seen_at", "first_seen_at"),
        Index("ix_events_domains", "domains", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_title: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_update_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    heat: Mapped[float] = mapped_column(Float, nullable=False, server_default="0", default=0.0)
    domains: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    tags: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    primary_entity_ids: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    snapshot_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("event_cards.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EventUpdateORM(Base):
    """event_updates 테이블 — append-only 변화분. EVENT_SCHEMA Part 2 §EventUpdate.

    불변식: INSERT 만(UPDATE/DELETE 금지) → 가역성·감사. event_id FK 는 **RESTRICT**(0006, ADR#20):
    감사 이력(변화분)이 있는 Event 는 DB 레벨에서 삭제 차단 — append-only 감사 trail 보호.
    """

    __tablename__ = "event_updates"
    __table_args__ = (
        Index("ix_event_updates_event_id_observed_at", "event_id", "observed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delta_summary: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    added_domains: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    source_refs: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    heat_delta: Mapped[float] = mapped_column(Float, nullable=False, server_default="0", default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def is_snapshot_bidirectional(
    event_id: Any,
    snapshot_card_id: Any,
    card_id: Any,
    card_event_id: Any,
) -> bool:
    """R-EventModelMigration 이중쓰기 정합성 불변식(EVENT_SCHEMA §1 심화 박스).

    events.snapshot_card_id 가 가리키는 카드의 event_id 는 그 event 를 역참조해야 한다(쌍방향 일관).
    카드↔Event 이중쓰기(스냅샷 갱신 + Event 연결) 시 두 FK 가 서로를 가리키는지 검증한다.
    UUID/str 혼용을 견디도록 문자열 비교한다. 네 값 중 하나라도 falsy(None/빈 문자열)면
    쌍방향 미성립(False) — 빈 문자열 id 를 유효 연결로 오인하지 않는다.
    """
    if not (event_id and snapshot_card_id and card_id and card_event_id):
        return False
    return str(snapshot_card_id) == str(card_id) and str(card_event_id) == str(event_id)
