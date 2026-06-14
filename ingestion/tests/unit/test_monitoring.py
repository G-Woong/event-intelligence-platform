"""F-11: Monitoring — summary/alert/critical 조건 + secret 미검출(네트워크 0)."""
from __future__ import annotations

import json

from ingestion.orchestration.monitoring import (
    Alert,
    build_alerts,
    build_monitoring_summary,
    write_monitoring_report,
)
from ingestion.orchestration.production_scheduler import ProductionRunPlan
from ingestion.orchestration.production_state import ProductionSourceState

_PASS_BRIDGE = {"raw_events_written": 3, "raw_events_skipped_duplicates": 1,
                "raw_events_held": 0, "raw_events_failed": 0, "target": "mirror",
                "bridge_contract_pass": True}


def _state(sid, status, *, ready=True, dead=False, reason=None):
    return ProductionSourceState(
        source_id=sid, enabled=True, excluded=False, source_group="news",
        expected_alive_type="ARTICLE_BODY_ALIVE", current_status=status,
        production_ready=ready, known_dead_end=dead, terminal_reason=reason)


def _plan(due, skipped, cats=None):
    return ProductionRunPlan(
        run_id="r1", created_at="2026-06-14T12:00:00Z", due_sources=tuple(due),
        skipped_sources=tuple(skipped), skipped_reasons={}, expected_calls=len(due),
        strategy_by_source={}, mode="production-validation", skip_category_counts=cats or {})


def test_clean_run_no_critical():
    states = [_state("bbc", "PRODUCTION_READY"), _state("ap_news", "PRODUCTION_READY")]
    plan = _plan(["bbc", "ap_news"], [])
    summary = build_monitoring_summary(
        run_id="r1", plan=plan, source_states=states, records_collected=3,
        eventqueue_written=3, duplicates_skipped=0, bridge_result=_PASS_BRIDGE,
        record_type_counts={"article_candidate": 3})
    assert summary["critical_alert_count"] == 0
    assert summary["source_without_state"] == 0


def test_raw_events_failure_is_critical():
    alerts = build_alerts(source_states=[], plan_due=1, plan_total=1, raw_events_failed=2,
                          eventqueue_failed=0, bridge_contract_pass=True)
    assert any(a.severity == "CRITICAL" and a.code == "raw_events_bridge_failure" for a in alerts)


def test_eventqueue_write_failure_is_critical():
    alerts = build_alerts(source_states=[], plan_due=1, plan_total=1, raw_events_failed=0,
                          eventqueue_failed=3, bridge_contract_pass=True)
    assert any(a.code == "eventqueue_write_failure" and a.severity == "CRITICAL" for a in alerts)


def test_bridge_contract_fail_is_critical():
    alerts = build_alerts(source_states=[], plan_due=1, plan_total=1, raw_events_failed=0,
                          eventqueue_failed=0, bridge_contract_pass=False)
    assert any(a.code == "raw_events_contract_fail" and a.severity == "CRITICAL" for a in alerts)


def test_source_without_state_is_critical():
    alerts = build_alerts(source_states=[], plan_due=1, plan_total=1, raw_events_failed=0,
                          eventqueue_failed=0, bridge_contract_pass=True, source_without_state=2)
    assert any(a.code == "source_without_state" and a.severity == "CRITICAL" for a in alerts)


def test_secret_exposure_suspected_is_critical():
    alerts = build_alerts(source_states=[], plan_due=1, plan_total=1, raw_events_failed=0,
                          eventqueue_failed=0, bridge_contract_pass=True,
                          secret_exposure_suspected=True)
    assert any(a.code == "secret_exposure_suspected" and a.severity == "CRITICAL" for a in alerts)


def test_all_sources_skipped_warning():
    alerts = build_alerts(source_states=[], plan_due=0, plan_total=10, raw_events_failed=0,
                          eventqueue_failed=0, bridge_contract_pass=True)
    assert any(a.code == "all_sources_skipped" and a.severity == "WARNING" for a in alerts)


def test_needs_operator_review_is_error():
    states = [_state("polygon", "NEEDS_OPERATOR_REVIEW", ready=False, reason="api_key_missing")]
    alerts = build_alerts(source_states=states, plan_due=0, plan_total=1, raw_events_failed=0,
                          eventqueue_failed=0, bridge_contract_pass=True)
    assert any(a.code == "needs_operator_review" and a.severity == "ERROR" for a in alerts)


def test_secret_in_payload_detected_via_summary():
    states = [_state("bbc", "PRODUCTION_READY")]
    plan = _plan(["bbc"], [])
    leaky = [{"url": "https://x.test?api_key=sk-secret123", "title": "t"}]
    summary = build_monitoring_summary(
        run_id="r1", plan=plan, source_states=states, records_collected=1,
        eventqueue_written=1, duplicates_skipped=0, bridge_result=_PASS_BRIDGE,
        queue_or_raw_sample=leaky)
    assert summary["critical_alert_count"] >= 1
    assert any(a["code"] == "secret_exposure_suspected" for a in summary["critical_alerts"])


def test_write_monitoring_report_creates_files(tmp_path):
    states = [_state("bbc", "PRODUCTION_READY")]
    plan = _plan(["bbc"], [])
    summary = build_monitoring_summary(
        run_id="r1", plan=plan, source_states=states, records_collected=1,
        eventqueue_written=1, duplicates_skipped=0, bridge_result=_PASS_BRIDGE)
    paths = write_monitoring_report(summary, states, monitoring_dir=tmp_path, run_id="r1")
    assert (tmp_path / "r1" / "production_summary.json").exists()
    assert (tmp_path / "r1" / "source_health.csv").exists()
    assert (tmp_path / "r1" / "alerts.json").exists()
    loaded = json.loads((tmp_path / "r1" / "production_summary.json").read_text(encoding="utf-8"))
    assert loaded["run_id"] == "r1"
