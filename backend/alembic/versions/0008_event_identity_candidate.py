"""event identity candidate (deterministic semantic cross-batch identity, ADR#41 / R-CrossBatchEventIdentity)

ADR#40 의 event_identity_map 은 **강한 anchor**(canonical_url/official_id record_key)가 배치를 넘어
**동일 재등장**할 때만 같은 사건을 잇는다(syndicated wire). 하지만 **다른 URL 의 두 기사가 같은 사건**
을 다른 배치에 보도하면 공유 anchor 가 없어 분열(UNDER-merge)된다 — 이 잔여를 보수적으로 줄인다.

이 테이블은 **결정론 semantic fingerprint**(publishable core 멤버 제목의 normalized token-set + date
bucket) → event_id 를 영속한다. event_identity_map(확정 anchor)과 **분리**한다(오염 금지): 후보는
"같은 사건일 수 있다"는 약한 신호라, 매칭 시 **자동 병합(APPEND)하지 않고** event_links(possible) 로만
링크한다(false-merge surface 0). 실제 병합은 미래 semantic adjudicator(embedding/LLM/KG)에게 이월한다.

candidate_key 는 String(256) PK(첫 매핑 보존 = on_conflict_do_nothing) — fingerprint 충돌 시 첫 Event 가
hub. FK RESTRICT(ADR#20 일관): 후보 매핑이 가리키는 Event 는 DB 레벨에서 삭제 차단(감사 보호).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-24 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # event_identity_candidate — deterministic semantic fingerprint → event_id (cross-batch 동일성 후보).
    # event_identity_map(확정 anchor)과 분리. 매칭은 LINK(possible)만 — 자동 병합 금지(false-merge 0).
    op.create_table(
        "event_identity_candidate",
        sa.Column("candidate_key", sa.String(length=256), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_event_identity_candidate_event_id", "event_identity_candidate", ["event_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_identity_candidate_event_id", table_name="event_identity_candidate"
    )
    op.drop_table("event_identity_candidate")
