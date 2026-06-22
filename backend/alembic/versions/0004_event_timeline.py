"""event timeline foundation (S1): events, event_updates, event_cards.event_id FK

ADR#16 / EVENT_SCHEMA Part 2. **Additive only** — 신규 테이블 + nullable 컬럼만. 기존 쓰기
경로 무수정(event_cards 기존 카드는 event_id NULL = degenerate Event, 정상 동작).
S1 스코프: events / event_updates / event_cards.event_id 만. cluster_event_map / event_links
는 S2(Resolution)로 이월.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # events — 안정 주제(사건). snapshot_card_id 는 기존 event_cards 를 가리킨다(존재함).
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_title", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_update_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("heat", sa.Float(), nullable=False, server_default="0"),
        sa.Column("domains", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("primary_entity_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "snapshot_card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_cards.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_events_heat", "events", ["heat"])
    op.create_index("ix_events_status", "events", ["status"])
    op.create_index("ix_events_last_update_at", "events", ["last_update_at"])
    op.create_index("ix_events_first_seen_at", "events", ["first_seen_at"])
    op.create_index("ix_events_domains", "events", ["domains"], postgresql_using="gin")

    # event_updates — append-only 변화분. 부모 Event 삭제 시 CASCADE.
    op.create_table(
        "event_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delta_summary", sa.String(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("added_domains", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("heat_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_event_updates_event_id_observed_at", "event_updates", ["event_id", "observed_at"]
    )

    # event_cards.event_id — 카드 = "특정 Event 의 한 스냅샷"(nullable, 기존 카드 비파괴).
    op.add_column("event_cards", sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_event_cards_event_id", "event_cards", "events", ["event_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_event_cards_event_id", "event_cards", ["event_id"])


def downgrade() -> None:
    # event_cards.event_id 와 event_updates.event_id 가 events 를 참조하므로 events 보다 먼저 제거.
    op.drop_index("ix_event_cards_event_id", table_name="event_cards")
    op.drop_constraint("fk_event_cards_event_id", "event_cards", type_="foreignkey")
    op.drop_column("event_cards", "event_id")

    op.drop_index("ix_event_updates_event_id_observed_at", table_name="event_updates")
    op.drop_table("event_updates")

    op.drop_index("ix_events_domains", table_name="events")
    op.drop_index("ix_events_first_seen_at", table_name="events")
    op.drop_index("ix_events_last_update_at", table_name="events")
    op.drop_index("ix_events_status", table_name="events")
    op.drop_index("ix_events_heat", table_name="events")
    op.drop_table("events")
