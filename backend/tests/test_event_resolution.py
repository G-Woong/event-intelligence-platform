from __future__ import annotations

"""S2a Event Resolution 토대 회귀 — ORM 형상 / Postgres DDL 문법 / Pydantic / 마이그레이션 체인.

DB 미연결(기존 backend 테스트 관례): 메타데이터 형상·DDL dialect 컴파일·순수 검증만. 실 Postgres
migration 실행은 범위 밖(S1과 동일). cluster_event_map/event_links 는 event_resolver(S2c)가 소비.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import String
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models.base import Base
from backend.app.models.event_resolution import ClusterEventMapORM, EventLinkORM
from backend.app.schemas.events import ClusterEventMap, EventLink


# ── ORM 메타데이터 ────────────────────────────────────────────────────────────
def test_resolution_tables_registered():
    assert "cluster_event_map" in Base.metadata.tables
    assert "event_links" in Base.metadata.tables


def test_cluster_event_map_columns_and_fk():
    cols = ClusterEventMapORM.__table__.columns
    cid = cols["cluster_id"]
    assert cid.primary_key is True
    assert isinstance(cid.type, String)
    eid = cols["event_id"]
    assert eid.nullable is False
    assert any(fk.target_fullname == "events.id" for fk in eid.foreign_keys)


def test_event_links_columns_and_fk():
    cols = EventLinkORM.__table__.columns
    for fk_col in ("event_id", "linked_event_id"):
        c = cols[fk_col]
        assert c.nullable is False
        assert any(fk.target_fullname == "events.id" for fk in c.foreign_keys)
    assert cols["status"].nullable is False
    assert cols["reason"].nullable is True


def test_metadata_sorts_with_resolution_tables():
    # cluster_event_map / event_links 는 events 만 참조(신규 순환 없음). sorted_tables 무에러.
    names = {t.name for t in Base.metadata.sorted_tables}
    assert {"events", "event_updates", "event_cards", "cluster_event_map", "event_links"} <= names


# ── Postgres DDL 컴파일 ───────────────────────────────────────────────────────
def test_cluster_event_map_ddl_compiles_for_postgres():
    ddl = str(CreateTable(ClusterEventMapORM.__table__).compile(dialect=postgresql.dialect()))
    assert "CREATE TABLE cluster_event_map" in ddl
    assert "cluster_id VARCHAR(256)" in ddl
    assert "REFERENCES events" in ddl and "CASCADE" in ddl


def test_event_links_ddl_compiles_for_postgres():
    ddl = str(CreateTable(EventLinkORM.__table__).compile(dialect=postgresql.dialect()))
    assert "CREATE TABLE event_links" in ddl
    assert "REFERENCES events" in ddl and "CASCADE" in ddl
    # status 허용값 CHECK 제약(자동병합 금지 상태집합 잠금).
    assert "ck_event_links_status" in ddl
    assert "possible" in ddl and "confirmed" in ddl


# ── Pydantic 스키마 ──────────────────────────────────────────────────────────
def test_cluster_event_map_pydantic():
    m = ClusterEventMap(cluster_id="xcluster:abc", event_id="evt-1")
    assert m.cluster_id == "xcluster:abc" and m.event_id == "evt-1"


def test_event_link_pydantic_defaults():
    link = EventLink(event_id="evt-1", linked_event_id="evt-2")
    assert link.status == "possible"  # 약신호 보류가 기본(자동병합 금지)
    assert link.reason is None
    assert isinstance(link.id, str)


def test_event_link_rejects_bad_status():
    with pytest.raises(ValidationError):
        EventLink(event_id="evt-1", linked_event_id="evt-2", status="merged_auto")


# ── alembic 0005 revision 체인 (텍스트 검증, import 안 함) ─────────────────────
def _migration_0005_text() -> str:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0005_event_resolution.py"
    return path.read_text(encoding="utf-8")


def test_migration_0005_revision_chain():
    text = _migration_0005_text()
    assert 'revision: str = "e5f6a7b8c9d0"' in text
    # 0004(event_timeline) 위에 쌓인다.
    assert 'down_revision: Union[str, None] = "d4e5f6a7b8c9"' in text
    assert "def upgrade()" in text and "def downgrade()" in text


def test_migration_0005_is_additive():
    text = _migration_0005_text()
    assert 'op.create_table(\n        "cluster_event_map"' in text
    assert 'op.create_table(\n        "event_links"' in text
    assert 'op.drop_table("event_links")' in text
    assert 'op.drop_table("cluster_event_map")' in text
