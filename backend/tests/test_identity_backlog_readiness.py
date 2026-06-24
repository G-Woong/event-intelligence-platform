"""ADR#48 — operational DB migration readiness: 결정론(비-DB) 단위 테스트.

async operational_db_readiness(DB 조회)는 live-PG 테스트에서 검증. 여기서는 chain/gap/destructive 순수 함수만.
"""
from __future__ import annotations

from backend.app.tools.identity_backlog_readiness import (
    STAGE3_REQUIRED_TABLES,
    build_operational_deploy_checklist,
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


# ── operational deploy checklist (ADR#50; 순수 함수 — 명령 문자열·executed=False) ─────────────
def _readiness(current):
    """compute_migration_gap → operational_db_readiness 형 dict(destructive/ready 보강)."""
    gap = compute_migration_gap(current, load_migration_chain())
    return {**gap, "destructive_risk": pending_destructive(gap["missing_revisions"]),
            "ready_for_stage3": current == _HEAD}


def test_deploy_checklist_operational_0003_pending_and_backup():
    # ADR#50(scenario 13·14·17): 운영 0003 → behind 6·pending revisions·backup 필수·executed False·ready False.
    c = build_operational_deploy_checklist(_readiness(_OPERATIONAL_0003))
    assert c["current_revision"] == _OPERATIONAL_0003
    assert c["target_revision"] == _HEAD
    assert c["behind_count"] == 6 and len(c["pending_revisions"]) == 6
    assert c["backup_required"] is True            # 무조건(운영 DB 변경 전)
    assert c["ready_for_stage3"] is False
    assert c["executed"] is False                  # 이 함수는 절대 실행 안 함(배포는 운영자 수동)


def test_deploy_checklist_commands_documented():
    # ADR#50(scenario 14~19·§6): upgrade/readiness/dry-run/persist/flag/backup/rollback 명령이 전부 문서화.
    c = build_operational_deploy_checklist(_readiness(_OPERATIONAL_0003))
    by_name = {s["name"]: s["cmd"] for s in c["steps"]}
    assert "alembic upgrade head" in by_name["upgrade"]
    assert "identity_backlog_readiness" in by_name["post_upgrade_readiness"]
    assert "--dry-run" in by_name["backfill_dry_run"]
    assert "--limit" in by_name["backfill_limited_persist"]
    assert "pg_dump" in by_name["backup"]
    assert "downgrade" in by_name["rollback_if_needed"]
    assert "EVENT_SEMANTIC_ADJUDICATION_ENABLED" in c["flags_to_enable"]
    assert "EVENT_RESOLUTION_ENABLED" in c["flags_to_enable"]
    assert c["rollback_guidance"]                  # 비어있지 않음


def test_deploy_checklist_on_head_still_backup_and_not_executed():
    # ADR#50(scenario 15·18): head 도달 시 pending 0 이어도 backup_required True·executed False(미실행 불변).
    c = build_operational_deploy_checklist(_readiness(_HEAD))
    assert c["behind_count"] == 0 and c["pending_revisions"] == []
    assert c["ready_for_stage3"] is True
    assert c["backup_required"] is True
    assert c["executed"] is False                  # upgrade 명령은 문서화만·실행 0
