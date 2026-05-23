"""raw_events table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-23 00:01:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(1024), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("theme_hint", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="collected"),
        sa.Column("enqueued_msg_id", sa.String(64), nullable=True),
        sa.Column("error_reason", sa.String(512), nullable=True),
        sa.Column(
            "raw_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_raw_events_content_hash"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_raw_events_source_external "
        "ON raw_events (source_type, external_id) WHERE external_id IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_raw_events_collected_at ON raw_events (collected_at DESC)")
    op.create_index("ix_raw_events_status", "raw_events", ["status"])
    op.create_index("ix_raw_events_source_type", "raw_events", ["source_type"])
    op.execute(
        "CREATE INDEX ix_raw_events_published_at ON raw_events (published_at DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX ix_raw_events_raw_metadata_gin "
        "ON raw_events USING gin (raw_metadata jsonb_path_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_raw_events_raw_metadata_gin")
    op.execute("DROP INDEX IF EXISTS ix_raw_events_published_at")
    op.drop_index("ix_raw_events_source_type", table_name="raw_events")
    op.drop_index("ix_raw_events_status", table_name="raw_events")
    op.execute("DROP INDEX IF EXISTS ix_raw_events_collected_at")
    op.execute("DROP INDEX IF EXISTS uq_raw_events_source_external")
    op.drop_table("raw_events")
