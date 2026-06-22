from __future__ import annotations

"""S1 Event 토대 회귀 — ORM 형상(메타데이터) / Postgres DDL 문법 / Pydantic / 불변식 헬퍼.

DB 미연결(기존 backend 테스트 관례와 동일): 메타데이터 형상·DDL dialect 컴파일·순수 함수만
검증한다 — 실 Postgres 가 이 DDL 을 수용하는지/마이그레이션이 실제로 도는지는 범위 밖이다
(measurement gate=mock 기반). 'consistency' 는 ORM↔마이그레이션 형상 정합 + 불변식 헬퍼 단위
검증을 뜻하며 3자(ORM↔마이그레이션↔실DB) 런타임 일치를 보증하지 않는다(adversarial N7).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models.base import Base
from backend.app.models.event import EventCardORM
from backend.app.models.event_timeline import (
    EventORM,
    EventUpdateORM,
    is_snapshot_bidirectional,
)
from backend.app.schemas.events import Event, EventUpdate


# ── ORM 메타데이터 ────────────────────────────────────────────────────────────
def test_timeline_tables_registered():
    assert "events" in Base.metadata.tables
    assert "event_updates" in Base.metadata.tables
    # S2a(2026-06-22): cluster_event_map / event_links 는 이제 등록됨(S1 이월 해소).
    # 상세 회귀는 test_event_resolution.py.
    assert "cluster_event_map" in Base.metadata.tables
    assert "event_links" in Base.metadata.tables


def test_metadata_sorts_without_circular_dependency():
    # events.snapshot_card_id ↔ event_cards.event_id 순환 FK 가 use_alter 로 분리돼
    # create_all/sorted_tables 가 CircularDependencyError 없이 동작해야 한다(adversarial B1).
    names = {t.name for t in Base.metadata.sorted_tables}
    assert {"events", "event_updates", "event_cards"} <= names


def test_events_columns_and_fk():
    cols = EventORM.__table__.columns
    assert cols["canonical_title"].nullable is False
    assert cols["status"].nullable is False
    assert cols["heat"].nullable is False
    for jsonb_col in ("domains", "tags", "primary_entity_ids"):
        assert cols[jsonb_col].nullable is False
    # snapshot_card_id 는 nullable + event_cards.id 역참조.
    snap = cols["snapshot_card_id"]
    assert snap.nullable is True
    assert any(fk.target_fullname == "event_cards.id" for fk in snap.foreign_keys)


def test_event_updates_columns_and_fk():
    cols = EventUpdateORM.__table__.columns
    # event_id 는 NOT NULL + events.id RESTRICT(0006, ADR#20 감사 보호).
    eid = cols["event_id"]
    assert eid.nullable is False
    assert any(fk.target_fullname == "events.id" for fk in eid.foreign_keys)
    assert cols["observed_at"].nullable is False
    assert cols["delta_summary"].nullable is False
    for jsonb_col in ("evidence", "added_domains", "source_refs"):
        assert cols[jsonb_col].nullable is False
    assert cols["heat_delta"].nullable is False


def test_event_cards_event_id_nullable_fk():
    # 비파괴 additive: 카드 = "특정 Event 의 스냅샷". NULL = degenerate(기존 카드 호환).
    col = EventCardORM.__table__.columns["event_id"]
    assert col.nullable is True
    assert any(fk.target_fullname == "events.id" for fk in col.foreign_keys)
    # 마이그레이션 0004 의 인덱스와 ORM 정합(드리프트 방지 — adversarial B2).
    assert "ix_event_cards_event_id" in {ix.name for ix in EventCardORM.__table__.indexes}


# ── Postgres DDL 컴파일(DB 연결 없이 dialect 컴파일) ──────────────────────────
def test_events_ddl_compiles_for_postgres():
    ddl = str(CreateTable(EventORM.__table__).compile(dialect=postgresql.dialect()))
    assert "CREATE TABLE events" in ddl
    assert "canonical_title VARCHAR(1024)" in ddl
    assert "JSONB" in ddl
    # snapshot_card_id FK 는 SET NULL.
    assert "event_cards" in ddl and "SET NULL" in ddl


def test_event_updates_ddl_compiles_for_postgres():
    ddl = str(CreateTable(EventUpdateORM.__table__).compile(dialect=postgresql.dialect()))
    assert "CREATE TABLE event_updates" in ddl
    # event_id FK 는 RESTRICT(0006, ADR#20 — 감사 이력 보호).
    assert "REFERENCES events" in ddl and "RESTRICT" in ddl


# ── Pydantic 스키마 ──────────────────────────────────────────────────────────
def test_event_schema_defaults_and_roundtrip():
    ev = Event(canonical_title="호르무즈 해협 긴장 고조")
    assert ev.status == "active"
    assert ev.heat == 0.0
    assert ev.domains == [] and ev.tags == [] and ev.primary_entity_ids == []
    assert ev.snapshot_card_id is None
    assert isinstance(ev.id, str)
    # round-trip
    again = Event.model_validate(ev.model_dump())
    assert again.id == ev.id and again.canonical_title == ev.canonical_title


def test_event_schema_rejects_bad_status():
    with pytest.raises(ValidationError):
        Event(canonical_title="x", status="bogus")


def test_event_update_schema_defaults():
    from datetime import datetime, timezone

    upd = EventUpdate(
        event_id="evt-1", observed_at=datetime.now(timezone.utc), delta_summary="유가 +4% 반응"
    )
    assert upd.evidence == [] and upd.added_domains == [] and upd.source_refs == []
    assert upd.heat_delta == 0.0
    assert isinstance(upd.id, str)


# ── 이중쓰기 정합성 불변식(R-EventModelMigration) ─────────────────────────────
def test_snapshot_bidirectional_consistent():
    # event.snapshot_card_id == card.id AND card.event_id == event.id → 일관.
    assert is_snapshot_bidirectional(
        event_id="evt-1", snapshot_card_id="card-9", card_id="card-9", card_event_id="evt-1"
    )


def test_snapshot_bidirectional_inconsistent_card_points_elsewhere():
    # card.event_id 가 다른 event 를 가리키면 불일치(드리프트 탐지).
    assert not is_snapshot_bidirectional(
        event_id="evt-1", snapshot_card_id="card-9", card_id="card-9", card_event_id="evt-OTHER"
    )


def test_snapshot_bidirectional_null_is_not_bidirectional():
    # degenerate 카드(event_id NULL)는 쌍방향 미성립 — 단독 카드로 정상이나 '연결'은 아님.
    assert not is_snapshot_bidirectional(
        event_id="evt-1", snapshot_card_id=None, card_id="card-9", card_event_id=None
    )


def test_snapshot_bidirectional_empty_string_is_false():
    # 빈 문자열 id 를 유효 연결로 오인하지 않는다(adversarial N3 거짓양성 차단).
    assert not is_snapshot_bidirectional(
        event_id="", snapshot_card_id="", card_id="", card_event_id=""
    )


def test_snapshot_bidirectional_uuid_str_mixed():
    import uuid

    eid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    cid = uuid.UUID("22222222-2222-2222-2222-222222222222")
    # ORM(UUID)↔schema(str) 혼용에도 문자열 비교로 일관 판정.
    assert is_snapshot_bidirectional(
        event_id=eid, snapshot_card_id=cid, card_id=str(cid), card_event_id=str(eid)
    )


# ── alembic 0004 revision 체인 ────────────────────────────────────────────────
# 마이그레이션 파일을 import 하지 않는다: pytest sys.path 에서 backend/alembic 가 설치된
# alembic 패키지를 가려 `from alembic import op` 가 깨진다(실제 alembic 런타임에선 정상).
# 텍스트로 revision 체인·additive 연산을 검증한다(DB 불필요, 런타임 비의존).
def _migration_0004_text() -> str:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0004_event_timeline.py"
    return path.read_text(encoding="utf-8")


def test_migration_0004_revision_chain():
    text = _migration_0004_text()
    assert 'revision: str = "d4e5f6a7b8c9"' in text
    # 0003(raw_events_event_card_link) 위에 쌓인다.
    assert 'down_revision: Union[str, None] = "c3d4e5f6a7b8"' in text
    assert "def upgrade()" in text and "def downgrade()" in text


def test_migration_0004_is_additive():
    text = _migration_0004_text()
    # additive: 신규 테이블 생성 + nullable 컬럼 추가만. 기존 컬럼 drop/alter 없어야 한다.
    assert 'op.create_table(\n        "events"' in text
    assert 'op.create_table(\n        "event_updates"' in text
    assert 'op.add_column("event_cards"' in text
    # downgrade 가 제공돼야 한다(롤백 가능).
    assert 'op.drop_table("events")' in text
    assert 'op.drop_table("event_updates")' in text
    assert 'op.drop_column("event_cards", "event_id")' in text
