"""복구 주기 드라이버 검증 (Orchestration 하드닝, Phase 3).

- 모든 action이 매 cycle에 실행된다.
- 한 action이 실패해도 다른 action과 루프가 중단되지 않는다(에러 격리).
- --once는 1회 cycle 후 종료한다(무한루프/sleep 없음).
"""
from __future__ import annotations

import workers.tools.run_recovery_scheduler as sched


def test_run_recovery_cycle_runs_all_actions():
    calls = []
    actions = [
        ("a", lambda: calls.append("a") or {"ok": 1}),
        ("b", lambda: calls.append("b") or {"ok": 2}),
    ]
    results = sched.run_recovery_cycle(actions)
    assert calls == ["a", "b"]
    assert results["a"] == {"ok": 1}
    assert results["b"] == {"ok": 2}


def test_run_recovery_cycle_isolates_failure():
    calls = []

    def boom():
        calls.append("boom")
        raise RuntimeError("redis down")

    actions = [
        ("reconcile", lambda: {"marked_failed": 0}),
        ("reap", boom),
        ("after", lambda: calls.append("after") or {"claimed": 0}),
    ]
    results = sched.run_recovery_cycle(actions)
    # 실패한 action은 error로 격리되고, 그 뒤 action도 실행된다.
    assert "error" in results["reap"]
    assert "RuntimeError" in results["reap"]["error"]
    assert results["after"] == {"claimed": 0}
    assert "after" in calls


def test_main_once_runs_single_cycle(monkeypatch):
    cycles = []
    monkeypatch.setattr(sched, "reconcile_stuck_action", lambda *a, **k: {"marked_failed": 0})
    monkeypatch.setattr(sched, "requeue_failed_xadd_action", lambda *a, **k: {"requeued": 0})
    monkeypatch.setattr(sched, "reap_pending_action", lambda *a, **k: {"claimed": 0, "retried": 0, "dead_lettered": 0})

    real_cycle = sched.run_recovery_cycle

    def spy(actions):
        cycles.append(1)
        return real_cycle(actions)

    monkeypatch.setattr(sched, "run_recovery_cycle", spy)

    # sleep이 호출되면 무한루프 의도이므로 --once에서는 호출되지 않아야 한다.
    monkeypatch.setattr(sched.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("should not sleep on --once")))

    rc = sched.main(["--once", "--dry-run"])
    assert rc == 0
    assert len(cycles) == 1


def test_main_once_returns_nonzero_when_all_actions_fail(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("backend unreachable")

    monkeypatch.setattr(sched, "reconcile_stuck_action", boom)
    monkeypatch.setattr(sched, "requeue_failed_xadd_action", boom)
    monkeypatch.setattr(sched, "reap_pending_action", boom)
    monkeypatch.setattr(sched.time, "sleep", lambda s: None)

    rc = sched.main(["--once"])
    # 모든 복구 action 실패 → cron이 성공으로 오인하지 않도록 non-zero.
    assert rc == 1
