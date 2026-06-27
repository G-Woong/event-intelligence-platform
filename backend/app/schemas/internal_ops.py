"""ADR#72 — internal ops dashboard read API 응답 스키마(InternalOpsPilotExecutionStatus).

`reviewer_pilot_execution.build_ops_ui_execution_contract` 가 산출하는 sanitized ops contract 를 그대로 미러한다.
이 스키마가 backend API 의 `response_model` 화이트리스트 역할을 한다 — same_event truth·reviewer raw PII·semantic
score·model rationale·predicted_status·secret 은 **필드 자체가 없어** 구조적으로 노출 불가(public truth 아님).
read-only workflow state 만 표현한다.
"""
from __future__ import annotations

from pydantic import BaseModel


class InternalOpsFlags(BaseModel):
    """internal ops dashboard no-go 플래그(전부 상수 — UI 가 truth/merge/public 으로 오인하지 못하게)."""
    internal_only: bool
    no_public_truth: bool
    no_merge: bool
    no_public_iu: bool
    pii_safe: bool
    no_llm: bool
    no_db_write: bool
    gold_provenance_verified: bool


class InternalOpsPilotExecutionStatus(BaseModel):
    """reviewer pilot 실행 workflow state(internal ops dashboard 전용·public truth 아님).

    counts·execution_status·calibration_gap·next_action·no-go flags 만 노출한다. production_gold_count 는
    `production_gold_provenance_verified`(현재 false) caveat 와 함께 — 미검증 gold 가 truth 로 박제되는 것 차단.
    """
    contract: str
    batch_id: str
    pilot_status: str
    execution_status: str
    contact_evidence_present: bool
    real_reviewers_contacted: int
    returned_label_count: int
    missing_label_count: int
    invalid_label_count: int
    invalid_file_count: int
    conflict_pair_count: int
    overdue_count: int
    production_gold_count: int
    synthetic_gold_count: int
    production_gold_provenance_verified: bool
    calibration_ready: bool
    merge_gate_ready: bool
    next_action: str
    flags: InternalOpsFlags
