"""D-1 운영 결선 composition root 단위 테스트(no DB).

backend/app/tools/run_event_orchestration 의 **결선 로직**을 검증한다:
  - flag OFF → sink 미주입(None) → ingestion 기존 동작 byte-identical
  - flag ON → sink 주입(callable) + 전용 엔진 생성·dispose(생명주기 소유)
  - 예외에도 finally 에서 engine.dispose(자원 정리)
  - default 는 settings.EVENT_RESOLUTION_ENABLED 를 따름(off-by-default)
  - main() 은 backend 전용 --event-resolution 만 소비, 나머지는 ingestion CLI 로 위임

실 DB 영속(sink 가 실제로 events 에 쓰는지)은 test_event_resolution_live_pg.py 의 live-PG
테스트가 검증한다(여기선 결선/생명주기/주입 여부만). sink 는 sync 경계에서 asyncio.run 으로
구동되므로 이 파일은 전부 sync 테스트다.
"""
from __future__ import annotations

import pytest

import backend.app.tools.run_event_orchestration as tool


class _RecordingEngine:
    """create_async_engine 대체용 fake. dispose 호출 여부만 기록(async dispose)."""

    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


def _stub_engine(monkeypatch) -> _RecordingEngine:
    eng = _RecordingEngine()
    monkeypatch.setattr(tool, "create_async_engine", lambda *a, **k: eng)
    # async_sessionmaker(engine) → factory. 테스트에선 factory() 가 호출되지 않으므로 더미면 충분.
    monkeypatch.setattr(tool, "async_sessionmaker", lambda *a, **k: (lambda: None))
    return eng


# ── run_event_orchestration: flag OFF/ON 주입 ────────────────────────────────────
def test_flag_off_sink_not_injected(monkeypatch):
    captured: dict = {}

    def fake_main(argv=None, *, event_resolution_sink=None):
        captured["argv"] = argv
        captured["sink"] = event_resolution_sink
        return 0

    monkeypatch.setattr(tool, "ingestion_main", fake_main)
    rc = tool.run_event_orchestration(["--mode", "production-dry-run"], enabled=False)

    assert rc == 0
    assert captured["sink"] is None                      # off → 미주입(기존 동작 보존)
    assert captured["argv"] == ["--mode", "production-dry-run"]


def test_flag_on_sink_injected_and_engine_disposed(monkeypatch):
    eng = _stub_engine(monkeypatch)
    captured: dict = {}

    def fake_main(argv=None, *, event_resolution_sink=None):
        captured["sink"] = event_resolution_sink
        return 0

    monkeypatch.setattr(tool, "ingestion_main", fake_main)
    rc = tool.run_event_orchestration([], enabled=True)

    assert rc == 0
    assert callable(captured["sink"])                    # on → sink 주입(callable)
    assert eng.disposed is True                          # 엔진 생명주기: dispose 호출


def test_engine_disposed_even_on_exception(monkeypatch):
    eng = _stub_engine(monkeypatch)

    def boom(argv=None, *, event_resolution_sink=None):
        raise RuntimeError("collection blew up")

    monkeypatch.setattr(tool, "ingestion_main", boom)
    with pytest.raises(RuntimeError):
        tool.run_event_orchestration([], enabled=True)
    assert eng.disposed is True                          # finally: 실패해도 자원 정리


# ── event_resolution_sink_cm: 생명주기/게이트 ────────────────────────────────────
def test_cm_off_creates_no_engine(monkeypatch):
    created = {"n": 0}

    def fake_engine(*a, **k):
        created["n"] += 1
        return _RecordingEngine()

    monkeypatch.setattr(tool, "create_async_engine", fake_engine)
    with tool.event_resolution_sink_cm(enabled=False) as sink:
        assert sink is None                              # off → DB 미접근
    assert created["n"] == 0                             # 엔진 생성 0(off-path 비용 0)


def test_cm_default_follows_settings(monkeypatch):
    # default(enabled=None) 는 settings 를 따른다.
    monkeypatch.setattr(tool.settings, "EVENT_RESOLUTION_ENABLED", False)
    with tool.event_resolution_sink_cm() as sink:
        assert sink is None

    eng = _stub_engine(monkeypatch)
    monkeypatch.setattr(tool.settings, "EVENT_RESOLUTION_ENABLED", True)
    with tool.event_resolution_sink_cm() as sink:
        assert callable(sink)
    assert eng.disposed is True


# ── main(): backend 전용 플래그 소비 + 위임 ──────────────────────────────────────
def test_main_strips_event_resolution_flag_and_enables(monkeypatch):
    captured: dict = {}

    def fake_run(argv=None, *, enabled=None):
        captured["argv"] = argv
        captured["enabled"] = enabled
        return 0

    monkeypatch.setattr(tool, "run_event_orchestration", fake_run)
    rc = tool.main(["--event-resolution", "--mode", "production-validation", "--all-due"])

    assert rc == 0
    assert "--event-resolution" not in captured["argv"]  # backend 전용 플래그는 소비
    assert captured["argv"] == ["--mode", "production-validation", "--all-due"]  # 나머지 위임
    assert captured["enabled"] is True


def test_main_without_flag_off_by_default(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(tool.settings, "EVENT_RESOLUTION_ENABLED", False)

    def fake_run(argv=None, *, enabled=None):
        captured["enabled"] = enabled
        return 0

    monkeypatch.setattr(tool, "run_event_orchestration", fake_run)
    tool.main(["--mode", "production-dry-run"])

    assert captured["enabled"] is False                  # off-by-default(플래그·설정 둘 다 꺼짐)


def test_main_flag_or_settings_enables(monkeypatch):
    # --event-resolution 없이도 settings 가 켜져 있으면 enabled.
    captured: dict = {}
    monkeypatch.setattr(tool.settings, "EVENT_RESOLUTION_ENABLED", True)
    monkeypatch.setattr(
        tool, "run_event_orchestration",
        lambda argv=None, *, enabled=None: captured.update(enabled=enabled) or 0,
    )
    tool.main(["--mode", "production-dry-run"])
    assert captured["enabled"] is True


# ── end-to-end: 실 orchestration 이 주입 sink 를 실제 호출(통합) ──────────────────
def test_end_to_end_real_ingestion_invokes_injected_sink(monkeypatch):
    # adversarial P6: backend CLI → **실 ingestion_main** → 실 orchestration → 주입 sink 호출까지
    # 전 구간을 1개 테스트로 잇는다(mock 으로 끊지 않음). dry-run 이라 network 0·DB 0(sink=spy).
    # 단위 테스트들은 ingestion_main 을 가짜화해 sink 를 받기만 했으나, 이 테스트는 실 orchestration
    # 이 주입된 sink 를 실제로 부르는 경로를 입증한다.
    eng = _stub_engine(monkeypatch)  # 실 엔진 대신 fake(dispose 기록), DATABASE_URL 미접근
    calls: dict = {"n": 0, "records": None}

    def spy(records, clusters=None):
        calls["n"] += 1
        calls["records"] = list(records)
        return {"enabled": True, "created": 0, "appended": 0}

    monkeypatch.setattr(tool, "make_orchestration_event_sink", lambda factory, *, enabled=None: spy)

    rc = tool.run_event_orchestration(["--mode", "production-dry-run", "--no-live"], enabled=True)

    assert rc == 0
    assert calls["n"] == 1            # 실 orchestration 이 주입 sink 를 실제 호출(0-coverage 구멍 차단)
    assert calls["records"] == []     # dry-run 이라 후보 0 — 경로는 살아있음(sink 진입 입증)
    assert eng.disposed is True       # 통합 경로에서도 엔진 생명주기 정리
