"""ADR#48 — operational DB migration readiness probe (read-only·non-destructive).

R-LiveIdentityBacklog 의 한 축은 **운영 DB 미마이그레이션**이다(probe: event_intel=0003·test=0009 HEAD).
이 모듈은 한 DB 의 alembic revision 과 identity 테이블 존재를 읽어 "stage③ 백로그를 누적할 준비가 됐는가"를
report 한다 — **read-only**(alembic_version/information_schema SELECT 만·DDL/upgrade 0). 운영 DB 실제
upgrade 적용은 **운영 배포 행위**라 이 모듈 밖이다(무단 destructive migration 금지).

migration chain 은 alembic 파일(revision/down_revision)에서 결정론으로 로드한다(linear chain 가정).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# stage③(semantic shadow adjudication)이 운영에서 백로그를 누적하려면 존재해야 하는 테이블.
STAGE3_REQUIRED_TABLES = (
    "events", "event_links", "event_identity_candidate", "event_identity_adjudication",
)
_ALL_PROBE_TABLES = ("events", "event_updates", "cluster_event_map", "event_links",
                     "event_identity_map", "event_identity_candidate", "event_identity_adjudication")

# revision/down_revision 라인(타입 어노테이션 `: str`/`: Union[str, None]` 허용).
_RE_REVISION = re.compile(r"""^revision\s*(?::[^=]+)?=\s*["']([^"']+)["']""", re.M)
_RE_DOWN = re.compile(r"""^down_revision\s*(?::[^=]+)?=\s*(?:["']([^"']+)["']|None)""", re.M)
# **데이터 손실** op 탐지(미적용 migration 의 위험도 표면화). drop_constraint(FK swap·0006)/create_*
# 는 데이터 손실 아님 → 제외(over-claim 방지). drop_table/drop_column 만 destructive_risk 로 본다.
_RE_DESTRUCTIVE = re.compile(r"op\.(drop_table|drop_column)\b")


def _default_versions_dir() -> Path:
    # backend/app/tools/identity_backlog_readiness.py → backend/alembic/versions
    return Path(__file__).resolve().parents[2] / "alembic" / "versions"


def load_migration_chain(versions_dir: Optional[Path] = None) -> list[str]:
    """alembic 파일 → revision id 순서 목록(base→head). linear chain 가정(분기 시 ValueError)."""
    vdir = Path(versions_dir) if versions_dir is not None else _default_versions_dir()
    down_of: dict[str, Optional[str]] = {}
    for f in vdir.glob("0*.py"):
        txt = f.read_text(encoding="utf-8")
        m_rev = _RE_REVISION.search(txt)
        if not m_rev:
            continue
        m_down = _RE_DOWN.search(txt)
        down_of[m_rev.group(1)] = m_down.group(1) if (m_down and m_down.group(1)) else None
    # base(down=None)부터 체인을 따라 head 까지 정렬.
    child_of: dict[Optional[str], str] = {}
    for rev, down in down_of.items():
        if down in child_of:
            raise ValueError(f"non-linear migration chain at {down!r}")
        child_of[down] = rev
    chain: list[str] = []
    cur: Optional[str] = None  # base 의 down_revision
    while cur in child_of:
        nxt = child_of[cur]
        chain.append(nxt)
        cur = nxt
    return chain


def compute_migration_gap(current_rev: Optional[str], chain: list[str]) -> dict:
    """현재 revision vs chain → gap(순수·결정론). current=None=base(아무것도 미적용)."""
    head = chain[-1] if chain else None
    if current_rev is None:
        missing = list(chain)
    elif current_rev in chain:
        missing = chain[chain.index(current_rev) + 1:]
    else:
        missing = []   # chain 밖 revision(미지) — 별도 표기
    return {
        "current_revision": current_rev,
        "expected_head": head,
        "missing_revisions": missing,
        "behind_count": len(missing),
        "on_head": current_rev == head and head is not None,
        "current_in_chain": current_rev is None or current_rev in chain,
    }


def pending_destructive(missing: list[str], versions_dir: Optional[Path] = None) -> bool:
    """미적용 migration 의 **upgrade() 본문**에 데이터 손실 op(drop_table/drop_column) 포함 여부.

    drop_*는 보통 downgrade() 에만 있으므로 **upgrade 영역만** 스캔한다(`def downgrade(` 이전) —
    upgrade 가 additive(create_*)면 destructive_risk=False(over-claim 방지)."""
    vdir = Path(versions_dir) if versions_dir is not None else _default_versions_dir()
    miss = set(missing)
    for f in vdir.glob("0*.py"):
        txt = f.read_text(encoding="utf-8")
        m_rev = _RE_REVISION.search(txt)
        if not (m_rev and m_rev.group(1) in miss):
            continue
        upgrade_body = txt.split("def downgrade(", 1)[0]   # upgrade() + 헤더만(downgrade 제외)
        if _RE_DESTRUCTIVE.search(upgrade_body):
            return True
    return False


async def _current_revision(session: AsyncSession) -> Optional[str]:
    """alembic_version.version_num 조회. 테이블 없으면(미초기화) None(=base)."""
    try:
        return (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
    except Exception:
        await session.rollback()
        return None


async def _present_tables(session: AsyncSession) -> set[str]:
    rows = (await session.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = ANY(:names)"
    ), {"names": list(_ALL_PROBE_TABLES)})).scalars().all()
    return set(rows)


async def operational_db_readiness(
    session: AsyncSession, *, db_name: str = "", versions_dir: Optional[Path] = None
) -> dict:
    """한 DB → migration/identity-table readiness report(**read-only**·DDL 0).

    ready_for_stage3 = stage③ 가 백로그를 누적할 테이블이 전부 존재. 운영 upgrade 적용은 이 모듈 밖(배포 행위)."""
    chain = load_migration_chain(versions_dir)
    current = await _current_revision(session)
    gap = compute_migration_gap(current, chain)
    present = await _present_tables(session)
    tables_present = {t: (t in present) for t in _ALL_PROBE_TABLES}
    ready = all(tables_present[t] for t in STAGE3_REQUIRED_TABLES)
    return {
        "db_name": db_name,
        "current_revision": gap["current_revision"],
        "expected_head": gap["expected_head"],
        "missing_revisions": gap["missing_revisions"],
        "behind_count": gap["behind_count"],
        "on_head": gap["on_head"],
        "tables_present": tables_present,
        "destructive_risk": pending_destructive(gap["missing_revisions"], versions_dir),
        "ready_for_stage3": ready,
    }
