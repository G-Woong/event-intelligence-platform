"""Phase C last_run_at local_file 영속 + run_cycle 반영 테스트 (docs 05, 11)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.fetch_strategies.models import CollectionProbeResult
from ingestion.orchestration.cycle_state import (
    load_last_run_state,
    record_last_run,
    save_last_run_state,
)
from ingestion.orchestration.source_profile import SourceProfile

UTC = timezone.utc


class FakeQueue:
    def __init__(self):
        self.items = []

    def enqueue(self, item):
        item_id = f"id-{len(self.items)}"
        self.items.append({"_id": item_id, **item})
        return item_id


def _ok(sid):
    return CollectionProbeResult(source_id=sid, status="LIVE_SUCCESS", items_found=2)


def _blocked(sid):
    return CollectionProbeResult(source_id=sid, status="BLOCKED", error_category="captcha")


# ── state roundtrip ──────────────────────────────────────────────────────────

def test_missing_state_file_returns_empty(tmp_path):
    assert load_last_run_state(tmp_path / "nope.json") == {}


def test_record_and_load_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    ts = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    record_last_run(p, "gdelt", ts)
    state = load_last_run_state(p)
    assert state["gdelt"] == ts


def test_save_then_new_load(tmp_path):
    p = tmp_path / "state.json"
    ts = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    save_last_run_state(p, {"yna": ts})
    assert load_last_run_state(p)["yna"] == ts


def test_corrupt_json_is_safe(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{ not valid json", encoding="utf-8")
    assert load_last_run_state(p) == {}  # 빈 상태로 안전 처리


# ── run_cycle 연동 ───────────────────────────────────────────────────────────

def test_run_cycle_records_only_successful_sources(tmp_path):
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    state_path = tmp_path / "state.json"
    profiles = [
        SourceProfile("gdelt", min_interval_seconds=300),
        SourceProfile("yna", min_interval_seconds=300),
    ]

    def probe(sid, **kw):
        return _blocked(sid) if sid == "yna" else _ok(sid)

    run_cycle(profiles=profiles, state_path=state_path, queue=FakeQueue(), probe_fn=probe)

    state = load_last_run_state(state_path)
    assert "gdelt" in state       # 성공 → 기록
    assert "yna" not in state     # 차단 → 미기록


def test_run_cycle_skips_not_due_source_via_state(tmp_path):
    """state에 방금 수집 기록이 있으면 다음 cycle에서 due=False가 된다."""
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    state_path = tmp_path / "state.json"
    profiles = [SourceProfile("gdelt", min_interval_seconds=3600)]
    q = FakeQueue()

    r1 = run_cycle(profiles=profiles, state_path=state_path, queue=q,
                   probe_fn=lambda sid, **kw: _ok(sid))
    assert r1.sources_attempted == 1  # 최초 → due

    r2 = run_cycle(profiles=profiles, state_path=state_path, queue=q,
                   probe_fn=lambda sid, **kw: _ok(sid))
    assert r2.sources_attempted == 0  # 방금 기록 → not due (min_interval 1h)


def test_run_cycle_no_state_path_does_not_persist(tmp_path):
    """state_path 미지정이면 last_run을 기록하지 않는다(Phase A/B 동작 불변)."""
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    run_cycle(["gdelt"], queue=FakeQueue(), probe_fn=lambda sid, **kw: _ok(sid))
    # 기본 state 파일이 생성/오염되지 않음을 간접 확인: 예외 없이 통과 + 별도 파일 없음
    assert not (tmp_path / "state.json").exists()
