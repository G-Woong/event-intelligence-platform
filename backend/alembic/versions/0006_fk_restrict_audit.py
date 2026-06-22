"""event timeline FK CASCADE -> RESTRICT (audit 보호, ADR#20)

S2e(live-PG) — Event 타임라인의 감사 이력(event_updates)·라우팅 메타(cluster_event_map)·링크
(event_links)가 Event 삭제와 함께 **조용히 cascade 삭제되지 않도록** FK ondelete 를 RESTRICT 로 전환.
ADR#20 의 app-layer no-delete 정책을 **DB 레벨에서도** 강제 — 의존 행이 있는 Event 는 DB 가 삭제 차단.

대상 FK 4개: event_updates.event_id · cluster_event_map.event_id · event_links.event_id ·
event_links.linked_event_id. (events.snapshot_card_id 의 SET NULL 은 유지 — 카드 삭제 시 스냅샷
포인터만 비움, 감사 손실 아님.)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (constraint_name, table, local_cols) — events.id 를 참조하는 FK 들.
_FKS = (
    ("event_updates_event_id_fkey", "event_updates", ["event_id"]),
    ("cluster_event_map_event_id_fkey", "cluster_event_map", ["event_id"]),
    ("event_links_event_id_fkey", "event_links", ["event_id"]),
    ("event_links_linked_event_id_fkey", "event_links", ["linked_event_id"]),
)


def _recreate(ondelete: str) -> None:
    for name, table, cols in _FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "events", cols, ["id"], ondelete=ondelete)


def upgrade() -> None:
    # CASCADE → RESTRICT: 의존 행이 있는 Event 삭제를 DB 레벨에서 차단(감사 보호).
    _recreate("RESTRICT")


def downgrade() -> None:
    # RESTRICT → CASCADE: 0005 시점 동작으로 복귀(가역).
    _recreate("CASCADE")
