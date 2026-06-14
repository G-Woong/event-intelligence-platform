"""Phase E-1: 소스별 trace logger (AuditTraceEvent / TraceRecorder)."""
from __future__ import annotations

import json

from ingestion.orchestration.audit_trace import AuditTraceEvent, TraceRecorder


def test_records_events_per_stage(tmp_path):
    rec = TraceRecorder("run1", jsonl_path=tmp_path / "trace.jsonl", console=False)
    rec.record("yna", "profile_loaded", "ok", timestamp="2026-06-14T00:00:00Z")
    rec.record("yna", "source_completed", "ok", timestamp="2026-06-14T00:00:01Z",
               metrics={"candidate_count": 3})
    assert len(rec.events_for("yna")) == 2
    assert rec.stage_counts() == {"profile_loaded": 1, "source_completed": 1}


def test_jsonl_written_one_line_per_event(tmp_path):
    path = tmp_path / "trace.jsonl"
    rec = TraceRecorder("run2", jsonl_path=path, console=False)
    rec.record("a", "probe_started", "ok", timestamp="t1")
    rec.record("b", "source_failed", "error", timestamp="t2", error_type="ValueError")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    row = json.loads(lines[1])
    assert row["source_id"] == "b"
    assert row["error_type"] == "ValueError"
    assert row["status"] == "error"


def test_secret_values_redacted_in_metrics(tmp_path):
    path = tmp_path / "trace.jsonl"
    rec = TraceRecorder("run3", jsonl_path=path, console=False)
    # 실수로 키성 메트릭이 들어와도 값은 마스킹되어야 한다(방어선).
    rec.record("x", "api_readiness_checked", "ok", timestamp="t",
               metrics={"api_key": "SHOULD_NOT_APPEAR", "count": 5})
    text = path.read_text(encoding="utf-8")
    assert "SHOULD_NOT_APPEAR" not in text
    assert "<redacted>" in text
    assert '"count": 5' in text


def test_event_to_dict_redacts_nested():
    ev = AuditTraceEvent(
        run_id="r", source_id="s", stage="probe_finished", status="ok",
        timestamp="t", message="m",
        metrics={"nested": {"secret": "X", "ok": 1}},
    )
    d = ev.to_dict()
    assert d["metrics"]["nested"]["secret"] == "<redacted>"
    assert d["metrics"]["nested"]["ok"] == 1


def test_recorder_survives_unwritable_path(tmp_path):
    # 로깅 실패가 audit을 죽이지 않는다(디렉토리를 파일로 막아도 예외 없이 진행).
    bad = tmp_path / "afile"
    bad.write_text("x", encoding="utf-8")
    rec = TraceRecorder("run4", jsonl_path=bad / "trace.jsonl", console=False)
    # 디렉토리 생성 시점에서 막혀도 record는 던지지 않는다.
    rec.record("s", "source_completed", "ok", timestamp="t")
    assert len(rec.events) == 1
