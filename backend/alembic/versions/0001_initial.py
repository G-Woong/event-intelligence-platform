"""Initial tables: event_cards + comments

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-05-23 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("theme", sa.String(), nullable=False),
        sa.Column("impact_path", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="published"),
        sa.Column(
            "sectors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "entities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
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
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_confidence_score_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX ix_event_cards_created_at ON event_cards (created_at DESC)")
    op.create_index("ix_event_cards_theme", "event_cards", ["theme"])
    op.execute(
        "CREATE INDEX ix_event_cards_sectors_gin ON event_cards USING gin (sectors jsonb_path_ops)"
    )
    op.create_index("ix_event_cards_status", "event_cards", ["status"])

    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["event_id"], ["event_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comments_event_id_created", "comments", ["event_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_comments_event_id_created", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_event_cards_status", table_name="event_cards")
    op.execute("DROP INDEX IF EXISTS ix_event_cards_sectors_gin")
    op.drop_index("ix_event_cards_theme", table_name="event_cards")
    op.execute("DROP INDEX IF EXISTS ix_event_cards_created_at")
    op.drop_table("event_cards")
