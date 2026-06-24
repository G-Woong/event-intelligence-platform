"""event identity adjudication (semantic adjudicator shadow/eval, ADR#42 / R-SemanticIdentityAdjudicator)

ADR#41 의 event_identity_candidate 는 공유 anchor 없는 같은-사건 후보를 `event_links(possible,
reason='semantic_cross_batch_candidate')` 로 **표면화만** 했다(소비처 0 = critic dead-data 지적).
이 테이블은 그 possible-link 를 소비하는 **첫 shadow/eval 계층**의 출력이다: deterministic adjudicator
가 두 Event 의 feature(title 유사도·날짜 거리·source_type·fingerprint/anchor 일치·evidence 수·언어)를
보고 status(likely_same_event / ambiguous / likely_different_event / insufficient_features)를 산출해
누적한다. **이 status 로 Event 를 자동 병합(APPEND)하지 않는다**(shadow only·중복 count 미감소·false-merge 0).
실제 병합은 labeled eval set + precision 입증 + adversarial 승인 전까지 금지(option C 금지).

link_id 는 event_links.id(UUID) PK — link 당 1 adjudication(idempotent, on_conflict 갱신). FK RESTRICT
(ADR#20 일관): adjudication 이 가리키는 link 는 DB 레벨에서 삭제 차단. **Additive only** — 신규 테이블 1개.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-24 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # event_identity_adjudication — semantic 후보 link 의 shadow/eval status (자동 병합 아님).
    op.create_table(
        "event_identity_adjudication",
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_links.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('likely_same_event', 'ambiguous', 'likely_different_event', 'insufficient_features')",
            name="ck_event_identity_adjudication_status",
        ),
    )
    op.create_index(
        "ix_event_identity_adjudication_status", "event_identity_adjudication", ["status"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_identity_adjudication_status", table_name="event_identity_adjudication"
    )
    op.drop_table("event_identity_adjudication")
