"""ADR#48 — operational DB migration readiness: 결정론(비-DB) 단위 테스트.

async operational_db_readiness(DB 조회)는 live-PG 테스트에서 검증. 여기서는 chain/gap/destructive 순수 함수만.
"""
from __future__ import annotations

from backend.app.tools.identity_backlog_readiness import (
    STAGE3_REQUIRED_TABLES,
    compute_migration_gap,
    load_migration_chain,
    pending_destructive,
)

# 실 alembic chain(0001~0009). head=0009 event_identity_adjudication.
_HEAD = "c9d0e1f2a3b4"
_BASE = "a1b2c3d4e5f6"
_OPERATIONAL_0003 = "c3d4e5f6a7b8"   # 운영 DB(event_intel) 실측 revision


def test_load_migration_chain_linear_base_to_head():
    chain = load_migration_chain()
    assert len(chain) == 9
    assert chain[0] == _BASE
    assert chain[-1] == _HEAD
    assert len(set(chain)) == len(chain)   # 중복 없음(linear)


def test_compute_gap_operational_0003_behind_six():
    # 운영 DB 0003 → 0004~0009 6 revision 누락(events/identity 테이블 부재의 근본 원인).
    chain = load_migration_chain()
    gap = compute_migration_gap(_OPERATIONAL_0003, chain)
    assert gap["behind_count"] == 6
    assert gap["on_head"] is False
    assert gap["current_in_chain"] is True
    assert gap["expected_head"] == _HEAD
    assert len(gap["missing_revisions"]) == 6
    assert _HEAD in gap["missing_revisions"]


def test_compute_gap_head_on_head():
    chain = load_migration_chain()
    gap = compute_migration_gap(_HEAD, chain)
    assert gap["behind_count"] == 0
    assert gap["on_head"] is True
    assert gap["missing_revisions"] == []


def test_compute_gap_base_none_all_missing():
    # alembic_version 테이블 없음(미초기화) → current=None → 전 chain 누락.
    chain = load_migration_chain()
    gap = compute_migration_gap(None, chain)
    assert gap["behind_count"] == 9
    assert gap["on_head"] is False
    assert gap["current_in_chain"] is True   # None(base) 은 chain 시작 전이라 valid


def test_compute_gap_unknown_revision_flagged():
    chain = load_migration_chain()
    gap = compute_migration_gap("deadbeefcafe", chain)
    assert gap["current_in_chain"] is False
    assert gap["missing_revisions"] == []     # chain 밖 → 별도 표기(임의 추정 안 함)


def test_pending_destructive_upgrade_additive_false():
    # 0004~0009 upgrade 는 전부 create_*(additive) — drop_table/column 은 downgrade 에만 → 데이터 손실 0.
    chain = load_migration_chain()
    missing = compute_migration_gap(_OPERATIONAL_0003, chain)["missing_revisions"]
    assert pending_destructive(missing) is False
    assert pending_destructive(chain) is False


def test_stage3_required_tables_cover_backlog():
    # stage③ 백로그 누적에 필요한 테이블(② link + ③ adjudication 포함).
    assert "event_links" in STAGE3_REQUIRED_TABLES
    assert "event_identity_adjudication" in STAGE3_REQUIRED_TABLES
    assert "event_identity_candidate" in STAGE3_REQUIRED_TABLES
