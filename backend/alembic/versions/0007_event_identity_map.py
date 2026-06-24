"""event identity map (cross-batch Event identity, ADR#40 / R-CrossBatchEventIdentity)

cluster_id(=xcluster:{min(member record_key)})는 cluster 멤버십에 의존해 배치마다 바뀔 수 있다 →
같은 사건이 새 corroborator 추가로 새 cluster_id→새 Event 로 분열(UNDER-merge). 이를 막기 위해
**cluster_id 와 분리된 결정론 Event identity 층**을 둔다: 강한 identity anchor(publishable 멤버의
canonical_url/official_id 기반 record_key) → event_id 매핑. 미매핑 cluster 가 CREATE 되기 전, 멤버의
identity anchor 가 이미 어떤 Event 에 속하면 그 Event 로 APPEND(분열 방지). **Additive only** — 신규 테이블 1개.

identity_key 는 cluster_event_map.cluster_id 와 같은 String(256) PK(첫 매핑 보존 = on_conflict_do_nothing).
FK RESTRICT(ADR#20 일관): identity 매핑이 가리키는 Event 는 DB 레벨에서 삭제 차단(감사 보호).

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-24 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # event_identity_map — strong identity anchor(record_key) → event_id (cross-batch 동일성 단일 출처).
    op.create_table(
        "event_identity_map",
        sa.Column("identity_key", sa.String(length=256), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_event_identity_map_event_id", "event_identity_map", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_event_identity_map_event_id", table_name="event_identity_map")
    op.drop_table("event_identity_map")
