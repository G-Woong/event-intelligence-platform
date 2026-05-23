"""raw_events: add event_card_id and processed_at columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-24 00:01:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "raw_events",
        sa.Column("event_card_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "raw_events",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_raw_events_event_card_id", "raw_events", ["event_card_id"])
    op.create_index("ix_raw_events_processed_at", "raw_events", ["processed_at"])


def downgrade() -> None:
    op.drop_index("ix_raw_events_processed_at", table_name="raw_events")
    op.drop_index("ix_raw_events_event_card_id", table_name="raw_events")
    op.drop_column("raw_events", "processed_at")
    op.drop_column("raw_events", "event_card_id")
