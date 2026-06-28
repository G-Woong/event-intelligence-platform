"""ADR#84 — sanitized live snapshot (reproducibility without leakage; gitignored outputs).

date-pinned bounded live run 의 **재현 가능한** 요약을 남긴다 — 단, raw body·secret·reviewer PII·per-pair score·
rationale·predicted_status·same_event truth 는 절대 포함하지 않는다(§8). named_entity/event_phrase 는 redact/hash
(원문 미노출)로만 기록한다. 산출 파일은 **outputs/ 하위(gitignored)** 에만 쓰고 **커밋하지 않는다**(상태/경로만 docs·
internal ops 에 노출). live attempt 가 없으면 `not_written_no_live_run`.

이 모듈은 새 사실을 만들지 않는다 — executor(`execute_date_pinned_bounded_live_run`) 결과의 **sanitized 투영**일 뿐.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "sanitized_live_snapshot"
# gitignored(outputs/ 전체가 .gitignore 대상) — 커밋 금지. 상태/경로만 노출.
_DEFAULT_SNAPSHOT_DIR = "outputs/live_snapshots"

SNAPSHOT_NOT_WRITTEN_NO_LIVE_RUN = "not_written_no_live_run"
SNAPSHOT_WRITTEN = "written"


def _redact_hash(text: Optional[str]) -> Optional[str]:
    """named_entity/event_phrase → sha256 단축 해시(원문 미노출·재현 식별만). 빈값 None."""
    t = (text or "").strip()
    if not t:
        return None
    return "sha256:" + hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


def build_sanitized_live_snapshot(
    target: dict, executor_out: dict, *, run_id: str, live_run_status: Optional[str] = None,
    date_window_enforced: bool = True,
) -> dict:
    """target(build_live_query_target) + executor_out(execute_date_pinned_bounded_live_run) → sanitized snapshot
    (§8·aggregate 만·per-pair score/raw body/secret/PII/same_event 0). PURE(no write).

    date_window_enforced 는 **실제 executor 호출 인자에서 파생**해 전달한다(상수 둔갑 금지·adversarial MEDIUM-2):
    enforce_window 적용 여부를 사실대로 기록해야 enforce 전/후 run 을 snapshot 으로 구분할 수 있다."""
    smoke = (executor_out or {}).get("smoke") or {}
    pcand = (executor_out or {}).get("pcand") or {}
    band = smoke.get("band_diagnostic") or {}
    probe = smoke.get("recall_probe_diagnostic") or {}
    executed = bool((executor_out or {}).get("executed"))

    snapshot = {
        "operation_name": OPERATION_NAME,
        "run_id": str(run_id),
        "live_query_executed": executed,
        # operator event 식별(원문 미노출·hash 만).
        "named_entity_redacted_or_hash": _redact_hash((target or {}).get("named_entity")),
        "event_phrase_redacted_or_hash": _redact_hash((target or {}).get("event_phrase")),
        "occurrence_date": (target or {}).get("occurrence_date"),
        "start_date": (target or {}).get("start_date"),
        "end_date": (target or {}).get("end_date"),
        "time_window": (target or {}).get("time_window"),
        "providers": list((target or {}).get("providers") or []),
        "date_window_enforced": bool(date_window_enforced),   # 실제 executor enforce_window 인자 반영(상수 아님).
        # live run aggregate(sanitized).
        "live_call_count": int((executor_out or {}).get("live_call_count") or 0),
        "executor_block_reason": (executor_out or {}).get("block_reason"),
        "provider_status_by_provider": dict(smoke.get("provider_status_by_provider") or {}),
        "records_count_by_provider": dict(smoke.get("records_count_by_provider") or {}),
        "comparison_pair_count": int(smoke.get("cross_source_pair_count") or 0),
        "max_baseline_jaccard": band.get("max_cross_source_title_jaccard"),
        "max_recall_probe_score": probe.get("max_recall_probe_score"),
        "live_pairs_newly_routed_by_probe": int(probe.get("pairs_newly_routed_by_probe") or 0),
        "production_candidate_status": pcand.get("production_candidate_status"),
        "production_frozen_pair_count": int(pcand.get("production_frozen_pair_count") or 0),
        "candidate_provenance": pcand.get("candidate_provenance") or "none",
        "live_run_status": live_run_status,
        "block_reasons": list(smoke.get("block_reasons") or []),
        "next_actions": list(pcand.get("next_actions") or [])[:3],
        # 경계(정직·constant·leakage 0).
        "raw_source_body_exposed": False,
        "secret_value_exposed": False,
        "per_pair_score_exposed": False,
        "rationale_exposed": False,
        "predicted_status_exposed": False,
        "same_event_truth_exposed": False,
        "raw_pii_exposed": False,
    }
    # 재귀 가드 — 정확명 forbidden-key(score/rationale/predicted_status/raw PII/secret)를 어떤 depth 든 차단
    # (값/substring 미검사·whitelisted 스키마 전제의 backstop·드리프트 fail-loud). entity/phrase 는 hash 만 저장.
    _assert_pii_safe(snapshot, _path="sanitized_live_snapshot")
    return snapshot


def write_sanitized_live_snapshot(
    snapshot: dict, *, directory: Optional[str] = None,
) -> dict:
    """sanitized snapshot 을 outputs/(gitignored)에 기록(커밋 금지). live attempt 없으면 미작성.
    반환: {snapshot_status, snapshot_path}. (path 만 노출 — 내용은 raw body/secret 0 이라도 outputs 전용.)"""
    if not snapshot.get("live_query_executed"):
        return {"snapshot_status": SNAPSHOT_NOT_WRITTEN_NO_LIVE_RUN, "snapshot_path": ""}
    base = Path(directory) if directory else Path(_DEFAULT_SNAPSHOT_DIR)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{snapshot.get('run_id')}.json"
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {"snapshot_status": SNAPSHOT_WRITTEN, "snapshot_path": str(path)}
