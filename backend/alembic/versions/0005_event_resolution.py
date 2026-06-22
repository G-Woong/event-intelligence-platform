"""event resolution routing (S2a): cluster_event_map, event_links

ADR#16 / EVENT_SCHEMA Part 2 §cluster_event_map·event_links. **Additive only** — 신규 테이블 2개.
S1(0004)에서 이월된 라우팅/링크 테이블. event_resolver(S2c)가 소비한다.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # cluster_event_map — cluster_id → event_id 라우팅 단일 진실원천.
    op.create_table(
        "cluster_event_map",
        sa.Column("cluster_id", sa.String(length=256), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cluster_event_map_event_id", "cluster_event_map", ["event_id"])

    # event_links — event ↔ event 링크(약신호 possible 보류, 자동병합 금지).
    op.create_table(
        "event_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "linked_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="possible"),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('possible', 'confirmed', 'rejected', 'merged')",
            name="ck_event_links_status",
        ),
    )
    op.create_index("ix_event_links_event_id", "event_links", ["event_id"])
    op.create_index("ix_event_links_status", "event_links", ["status"])


def downgrade() -> None:
    op.drop_index("ix_event_links_status", table_name="event_links")
    op.drop_index("ix_event_links_event_id", table_name="event_links")
    op.drop_table("event_links")
    op.drop_index("ix_cluster_event_map_event_id", table_name="cluster_event_map")
    op.drop_table("cluster_event_map")
