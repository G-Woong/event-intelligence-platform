"""Phase F-11 Monitoring / Health Report — 운영 모니터링 산출물.

run별로 production_summary.json / source_health.csv / alerts.json을 생성한다(모두
gitignored outputs). 지표는 source별 health/latency/success/failure/dedup/queue/raw_events를
포함한다. CRITICAL alert 조건(raw_events bridge 실패, EventQueue write 실패, secret 노출 의심,
모든 source 예기치 않게 skip, final state 없는 source)을 검출한다.

monitoring은 장식이 아니다 — runner의 exit code와 verdict가 여기서 나온 critical alert에
의존한다. 신규 설치 0(stdlib json/csv).
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

SEV_INFO = "INFO"
SEV_WARNING = "WARNING"
SEV_ERROR = "ERROR"
SEV_CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Alert:
    severity: str
    code: str
    message: str
    source_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def build_alerts(
    *,
    source_states,
    plan_due: int,
    plan_total: int,
    raw_events_failed: int,
    eventqueue_failed: int,
    bridge_contract_pass: bool,
    secret_exposure_suspected: bool = False,
    source_without_state: int = 0,
    external_errors: int = 0,
    quarantined: int = 0,
) -> list[Alert]:
    """집계 지표 → Alert 목록. CRITICAL은 launch/exit를 막는 조건."""
    alerts: list[Alert] = []

    if raw_events_failed > 0:
        alerts.append(Alert(SEV_CRITICAL, "raw_events_bridge_failure",
                            f"{raw_events_failed} raw_events write failures"))
    if not bridge_contract_pass:
        alerts.append(Alert(SEV_CRITICAL, "raw_events_contract_fail",
                            "raw_events bridge contract did not pass (schema failures)"))
    if eventqueue_failed > 0:
        alerts.append(Alert(SEV_CRITICAL, "eventqueue_write_failure",
                            f"{eventqueue_failed} EventQueue write failures"))
    if secret_exposure_suspected:
        alerts.append(Alert(SEV_CRITICAL, "secret_exposure_suspected",
                            "potential secret detected in output payload"))
    if source_without_state > 0:
        alerts.append(Alert(SEV_CRITICAL, "source_without_state",
                            f"{source_without_state} source(s) without final production state"))
    # 모든 source가 예기치 않게 skip (due 0인데 전체가 운영가능 상태였어야 함)
    if plan_total > 0 and plan_due == 0:
        alerts.append(Alert(SEV_WARNING, "all_sources_skipped",
                            "no due sources in this run (verify cadence/cooldown if unexpected)"))

    if external_errors > 0:
        alerts.append(Alert(SEV_WARNING, "external_errors",
                            f"{external_errors} source(s) in external error/blocked state"))
    if quarantined > 0:
        alerts.append(Alert(SEV_WARNING, "quarantined_sources",
                            f"{quarantined} source(s) quarantined"))

    # NEEDS_OPERATOR_REVIEW source는 ERROR(운영자 조치 필요)
    for s in source_states:
        if getattr(s, "current_status", None) == "NEEDS_OPERATOR_REVIEW":
            alerts.append(Alert(SEV_ERROR, "needs_operator_review",
                                f"{s.source_id} needs operator action: {s.terminal_reason}",
                                source_id=s.source_id))
    return alerts


def _scan_secret_suspect(records) -> bool:
    """queue/raw_events payload에 secret 흔적이 있는지 보수적 검사.

    `api_key=`/`apikey=`/`secret=`/`bearer` 등 키-할당 형태는 보수적 substring으로 잡고,
    `sk-` 같은 토큰형 패턴은 정식 스캐너(scan_secrets.text_has_secret)의 단어경계+고엔트로피
    판별을 재사용한다. naive `"sk-"` substring은 기사 URL slug(`musk-`/`risk-`/`samsung-sk-hynix`)를
    오탐해 매 production run을 거짓 CRITICAL로 만들었다 — 정식 스캐너와 판정을 일치시킨다.
    """
    from ingestion.tools.scan_secrets import text_has_secret

    needles = ("api_key=", "apikey=", "authorization: bearer", "bearer ey", "secret=")
    for rec in records:
        try:
            blob = json.dumps(rec, ensure_ascii=False)
        except (TypeError, ValueError):
            continue
        if any(n in blob.lower() for n in needles):
            return True
        if text_has_secret(blob):
            return True
    return False


def build_monitoring_summary(
    *,
    run_id: str,
    plan,
    source_states,
    records_collected: int,
    eventqueue_written: int,
    duplicates_skipped: int,
    bridge_result: dict,
    record_type_counts: Optional[dict] = None,
    body_present_count: int = 0,
    time_precision: Optional[dict] = None,
    eventqueue_failed: int = 0,
    queue_or_raw_sample: Optional[list] = None,
    avg_latency_ms: Optional[float] = None,
    error_by_source: Optional[dict] = None,
    error_by_root_cause: Optional[dict] = None,
) -> dict:
    """run의 모든 지표를 모은 production summary dict + alerts 산출."""
    from ingestion.orchestration.production_state import summarize_states

    states = list(source_states)
    state_summary = summarize_states(states)
    record_type_counts = record_type_counts or {}

    external_errors = sum(1 for s in states if s.current_status in (
        "EXTERNAL_API_ERROR", "EXTERNAL_RATE_LIMITED", "POLICY_BLOCKED_NO_BYPASS",
        "VENDOR_CONTRACT_REQUIRED", "NOT_SERVICE_USEFUL",
    ))
    quarantined = sum(1 for s in states if s.current_status == "QUARANTINED")
    cooldown = sum(1 for s in states if s.current_status == "COOLDOWN")

    secret_suspect = _scan_secret_suspect(queue_or_raw_sample or [])

    alerts = build_alerts(
        source_states=states,
        plan_due=len(plan.due_sources), plan_total=len(plan.due_sources) + len(plan.skipped_sources),
        raw_events_failed=bridge_result.get("raw_events_failed", 0),
        eventqueue_failed=eventqueue_failed,
        bridge_contract_pass=bridge_result.get("bridge_contract_pass", False),
        secret_exposure_suspected=secret_suspect,
        source_without_state=state_summary["source_without_state"],
        external_errors=external_errors, quarantined=quarantined,
    )
    critical = [a for a in alerts if a.severity == SEV_CRITICAL]

    skip_cats = getattr(plan, "skip_category_counts", {}) or {}
    summary = {
        "run_id": run_id,
        "mode": plan.mode,
        "source_total": len(states),
        "due_sources": len(plan.due_sources),
        "attempted_sources": len(plan.due_sources),
        "skipped_policy": skip_cats.get("skipped_policy", 0),
        "skipped_cooldown": skip_cats.get("skipped_cooldown", 0),
        "skipped_quarantine": skip_cats.get("skipped_quarantine", 0),
        "skipped_dead_end": skip_cats.get("skipped_dead_end", 0),
        "skipped_not_due": skip_cats.get("skipped_not_due", 0),
        "rate_limited": cooldown,
        "external_errors": external_errors,
        "quarantined": quarantined,
        "records_collected": records_collected,
        "records_enqueued": eventqueue_written,
        "duplicates_skipped": duplicates_skipped,
        "raw_events_written": bridge_result.get("raw_events_written", 0),
        "raw_events_skipped_duplicates": bridge_result.get("raw_events_skipped_duplicates", 0),
        "raw_events_held": bridge_result.get("raw_events_held", 0),
        "raw_events_failed": bridge_result.get("raw_events_failed", 0),
        "bridge_target": bridge_result.get("target"),
        "bridge_contract_pass": bridge_result.get("bridge_contract_pass", False),
        "body_present_count": body_present_count,
        "structured_signal_count": record_type_counts.get("structured_signal", 0),
        "official_record_count": record_type_counts.get("official_record", 0),
        "search_result_count": record_type_counts.get("search_result", 0),
        "community_signal_count": record_type_counts.get("community_signal", 0),
        "article_candidate_count": record_type_counts.get("article_candidate", 0),
        "avg_latency_ms": avg_latency_ms,
        "time_precision": time_precision or {},
        "state_distribution": state_summary["distribution"],
        "source_without_state": state_summary["source_without_state"],
        "unknown_root_cause": state_summary["unknown"],
        "error_by_source": error_by_source or {},
        "error_by_root_cause": error_by_root_cause or {},
        "alerts": [a.to_dict() for a in alerts],
        "critical_alerts": [a.to_dict() for a in critical],
        "critical_alert_count": len(critical),
    }
    return summary


def write_monitoring_report(
    summary: dict,
    source_states,
    *,
    monitoring_dir: str | Path,
    run_id: str,
) -> dict:
    """summary + source_health.csv + alerts.json을 run 디렉터리에 기록. 경로 dict 반환."""
    base = Path(monitoring_dir) / run_id
    base.mkdir(parents=True, exist_ok=True)

    summary_path = base / "production_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    health_path = base / "source_health.csv"
    with open(health_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "source_id", "current_status", "production_ready", "known_dead_end",
            "best_strategy", "failure_count", "consecutive_failure_count",
            "cooldown_until", "quarantine_until", "terminal_reason",
        ])
        for s in sorted(source_states, key=lambda x: x.source_id):
            w.writerow([
                s.source_id, s.current_status, s.production_ready, s.known_dead_end,
                s.best_strategy or "", s.failure_count, s.consecutive_failure_count,
                s.cooldown_until or "", s.quarantine_until or "", s.terminal_reason or "",
            ])

    alerts_path = base / "alerts.json"
    alerts_path.write_text(
        json.dumps({"run_id": run_id, "alerts": summary.get("alerts", []),
                    "critical_alerts": summary.get("critical_alerts", [])},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "summary_path": str(summary_path),
        "source_health_path": str(health_path),
        "alerts_path": str(alerts_path),
    }
