"""ADR#51 — backfill operation hardening (preflight gate · exit code · scheduler) 결정론 테스트.

실 DB 없이(monkeypatch) 다음 **정책**을 잠근다:
  - decide_exit_code: ran/blocked · dry-run pending → deterministic exit code(0/1/3).
  - backfill_preflight: ready_for_stage3 hard gate + flag persist gate → persist_allowed 매트릭스.
  - run_semantic_backfill_scheduler.main: safe-target fail-fast · --once exit code 전파 · tick 예외 격리.

DB orchestration(실 readiness · cursor_mode='created_at' 시간순 · persist gate)은 live-PG(test_event_resolution_live_pg)에서.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from backend.app.tools import backfill_semantic_adjudications as bf
from workers.tools import run_semantic_backfill_scheduler as sched


def _report(**over) -> dict:
    base = dict(
        dry_run=False, limit=100, cursor_mode="created_at", after_link_id=None, after_created_at=None,
        pending_before=0, processed=0, pending_after=0, by_status={}, event_count_before=0,
        event_count_after=0, next_cursor=None, next_created_at=None, full_scan=False,
        idempotent_persist=True, auto_merge_enabled=False,
    )
    base.update(over)
    return base


def _preflight(**over) -> dict:
    base = dict(ready_for_stage3=True, current_revision="c9d0e1f2a3b4", behind_count=0,
                flag_enabled=True, allow_flag_off=False, persist_allowed=True)
    base.update(over)
    return base


# ── decide_exit_code (pure) ──────────────────────────────────────────────────────────
def test_decide_exit_code_blocked_is_1():
    assert bf.decide_exit_code({"ran": False, "block": "readiness"}) == 1
    assert bf.decide_exit_code({"ran": False, "block": "flag"}) == 1


def test_decide_exit_code_dry_run_pending_is_3():
    # dry-run 으로 백로그 미배수(pending 남음) → 정보용 nonzero 3.
    assert bf.decide_exit_code({"ran": True, "report": _report(dry_run=True, pending_after=2)}) == 3


def test_decide_exit_code_success_is_0():
    assert bf.decide_exit_code({"ran": True, "report": _report(dry_run=True, pending_after=0)}) == 0   # dry-run·pending 0
    assert bf.decide_exit_code({"ran": True, "report": _report(dry_run=False, pending_after=0)}) == 0  # persist 성공


# ── backfill_preflight persist_allowed 매트릭스 (monkeypatch readiness + flag) ──────────
def _patch_readiness(monkeypatch, *, ready: bool):
    async def _fake(*_a, **_k):
        return {"ready_for_stage3": ready, "current_revision": "x", "behind_count": 0 if ready else 6}
    monkeypatch.setattr(bf, "operational_db_readiness", _fake)


def test_preflight_ready_flag_on_allows_persist(monkeypatch):
    _patch_readiness(monkeypatch, ready=True)
    monkeypatch.setattr(bf.settings, "EVENT_SEMANTIC_ADJUDICATION_ENABLED", True)
    pre = asyncio.run(bf.backfill_preflight(None))
    assert pre["ready_for_stage3"] is True and pre["flag_enabled"] is True
    assert pre["persist_allowed"] is True


def test_preflight_ready_flag_off_blocks_persist(monkeypatch):
    _patch_readiness(monkeypatch, ready=True)
    monkeypatch.setattr(bf.settings, "EVENT_SEMANTIC_ADJUDICATION_ENABLED", False)
    pre = asyncio.run(bf.backfill_preflight(None))
    assert pre["persist_allowed"] is False   # flag off → persist 불가(dry-run 은 ready 만으로 가능)


def test_preflight_allow_flag_off_overrides(monkeypatch):
    _patch_readiness(monkeypatch, ready=True)
    monkeypatch.setattr(bf.settings, "EVENT_SEMANTIC_ADJUDICATION_ENABLED", False)
    pre = asyncio.run(bf.backfill_preflight(None, allow_flag_off=True))
    assert pre["persist_allowed"] is True    # 명시 우회


def test_preflight_not_ready_blocks_even_flag_on(monkeypatch):
    _patch_readiness(monkeypatch, ready=False)
    monkeypatch.setattr(bf.settings, "EVENT_SEMANTIC_ADJUDICATION_ENABLED", True)
    pre = asyncio.run(bf.backfill_preflight(None))
    assert pre["ready_for_stage3"] is False and pre["persist_allowed"] is False   # ready hard gate


# ── run_backfill_with_preflight 게이트 분기 (monkeypatch preflight + backfill) ──────────
def test_with_preflight_not_ready_does_not_run(monkeypatch):
    async def _pre(*_a, **_k):
        return _preflight(ready_for_stage3=False, persist_allowed=False)
    monkeypatch.setattr(bf, "backfill_preflight", _pre)
    called = {"n": 0}

    async def _bf(*_a, **_k):
        called["n"] += 1
        return _report()
    monkeypatch.setattr(bf, "backfill_semantic_adjudications", _bf)
    out = asyncio.run(bf.run_backfill_with_preflight(None, dry_run=True))   # dry-run 도 not-ready 면 미실행
    assert out["ran"] is False and out["block"] == "readiness" and called["n"] == 0


def test_with_preflight_flag_block_does_not_persist(monkeypatch):
    async def _pre(*_a, **_k):
        return _preflight(persist_allowed=False)   # ready True·flag off
    monkeypatch.setattr(bf, "backfill_preflight", _pre)

    async def _bf(*_a, **_k):
        return _report()
    monkeypatch.setattr(bf, "backfill_semantic_adjudications", _bf)
    out = asyncio.run(bf.run_backfill_with_preflight(None, dry_run=False))   # persist 요청
    assert out["ran"] is False and out["block"] == "flag"


# ── scheduler main (safe-target · --once exit code · tick 예외 격리) ─────────────────────
def _patch_session(monkeypatch, fake):
    """scheduler._run_cycle 가 호출하는 bf.run_backfill_session 을 async fake 로 치환."""
    monkeypatch.setattr(bf, "run_backfill_session", fake)


def test_scheduler_safe_target_block_exit_1(monkeypatch):
    # APP_ENV=staging(비-dev) → assert_safe_write_target 가 DB 접근 전 차단 → exit 1.
    monkeypatch.setattr(sched.settings, "APP_ENV", "staging")
    assert sched.main(["--once"]) == 1


def test_scheduler_once_success_exit_0(monkeypatch):
    async def _ok(**_k):
        return {"ran": True, "block": None, "preflight": _preflight(),
                "report": _report(dry_run=False, pending_after=0)}
    _patch_session(monkeypatch, _ok)
    assert sched.main(["--once", "--persist"]) == 0


def test_scheduler_once_blocked_exit_1(monkeypatch):
    async def _blocked(**_k):
        return {"ran": False, "block": "readiness", "preflight": _preflight(ready_for_stage3=False)}
    _patch_session(monkeypatch, _blocked)
    assert sched.main(["--once", "--persist"]) == 1


def test_scheduler_once_dry_run_pending_exit_3(monkeypatch):
    async def _dry(**_k):
        return {"ran": True, "block": None, "preflight": _preflight(),
                "report": _report(dry_run=True, pending_after=1)}
    _patch_session(monkeypatch, _dry)
    assert sched.main(["--once"]) == 3   # 기본 dry-run(--persist 없음)·pending 남음


def test_scheduler_once_runtime_error_exit_2(monkeypatch):
    async def _boom(**_k):
        raise RuntimeError("boom")
    _patch_session(monkeypatch, _boom)
    assert sched.main(["--once", "--persist"]) == 2   # tick 예외 격리 → exit 2(루프 미중단)


# ── docker compose 일관성 (ADR#52: semantic-backfill-scheduler 안전 속성 잠금) ──────────
# scheduler 를 실제 docker 서비스로 배선하되 **기본 미가동·dry-run default** 가 silent 회귀하지 않도록
# compose 정의를 정적 파싱해 검증한다(build/up 안 함 — 정의만). runbook/compose 불일치 방지.
def _compose_service(name: str = "semantic-backfill-scheduler") -> dict:
    path = Path(__file__).resolve().parents[2] / "docker-compose.dev.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc["services"][name]


def test_compose_scheduler_service_exists_and_profile_gated():
    svc = _compose_service()
    # profile-gated → `docker compose up` 기본 스택에 미기동(--profile backfill 명시해야 기동).
    assert svc.get("profiles") == ["backfill"]


def test_compose_scheduler_dry_run_default_no_persist():
    svc = _compose_service()
    cmd = svc.get("command") or []
    tokens = cmd if isinstance(cmd, list) else str(cmd).split()
    assert "--persist" not in tokens   # command 에 --persist 없음 = dry-run default(영속 0)


def test_compose_scheduler_entrypoint_is_scheduler_module():
    svc = _compose_service()
    ep = svc.get("entrypoint") or []
    tokens = ep if isinstance(ep, list) else str(ep).split()
    # backend entrypoint.sh(alembic+uvicorn) 우회 — scheduler 모듈 직접 구동.
    assert "workers.tools.run_semantic_backfill_scheduler" in tokens
    assert "uvicorn" not in tokens


def test_compose_scheduler_db_target_and_postgres_dep():
    svc = _compose_service()
    assert "DATABASE_URL" in (svc.get("environment") or {})       # write target 명시
    assert "postgres" in (svc.get("depends_on") or {})            # DB healthy 후 기동


def test_compose_scheduler_single_instance_no_replicas():
    svc = _compose_service()
    # 동시성 경계: 단일 instance(중복 work 회피·ADR#52 ⓓ) — replicas 미설정·restart 자동부활 아님.
    replicas = (svc.get("deploy") or {}).get("replicas")
    assert replicas in (None, 1)
    assert str(svc.get("restart", "no")) in ("no", "false", "False")
