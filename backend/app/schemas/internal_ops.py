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


class InternalOpsReadinessStage(BaseModel):
    """R1~R7 gated roadmap 단계(읽기 전용 요약·gold→MERGE_GATE→embedding→entity→KG→GraphRAG→IU).

    안전 roadmap 텍스트만(score/rationale/predicted_status/PII 필드 없음). public IU 는 모든 gate 통과 전 No-Go.
    """
    stage: str
    goal: str
    current_status: str
    blocker: str
    next_action: str


class InternalOpsPreflightStatus(BaseModel):
    """ADR#73 — internal ops auth/deploy preflight + product bridge readiness(read-only·public truth 아님).

    `internal_ops_preflight.run_internal_ops_preflight` 의 sanitized contract 를 미러한다. auth/deploy posture
    (5-state)·R1~R7 readiness 만 노출한다 — admin token **값**은 필드 자체가 없고 `admin_token_configured`(존재
    여부 bool)만 표면화한다(secret 0). same_event truth·score·rationale·predicted_status·raw PII 미노출.
    """
    contract: str
    preflight_status: str
    auth_boundary_status: str
    app_env: str
    admin_token_required: bool
    admin_token_configured: bool
    feature_flag_required: bool
    feature_flag_enabled: bool
    frontend_server_env_required: bool
    public_nav_exposed: bool
    deployment_proven: bool
    actual_input_status: str
    external_input_required: bool
    production_gold_count: int
    calibration_ready: bool
    merge_gate_ready: bool
    # 매트릭스 **구조 정합**(7단계)일 뿐 — 단계 통과 아님. 실 단계 상태는 r1_r7_stages[].current_status(R1 현재 FAIL).
    r1_r7_readiness_matrix_ready: bool
    r1_r7_stages: list[InternalOpsReadinessStage]
    flags: InternalOpsFlags
    block_reasons: list[str]
    next_actions: list[str]


class InternalOpsR1AcquisitionStatus(BaseModel):
    """ADR#74 — R1 production gold acquisition operating plan(read-only·public truth 아님).

    `r1_gold_acquisition_plan.run_r1_gold_acquisition_plan` 의 sanitized r1_contract 를 미러한다. R1 status
    (4-state)·gold floor current/required·gap·reviewer 요구·operator next manual action 만 노출한다 — same_event
    truth·score·rationale·predicted_status·raw PII·secret 은 필드 자체가 없어 구조적 미노출. target floor 는
    *operating floor* 이지 production truth 가 아니다(R1 satisfied 는 calibration_ready 일 때만).
    """
    contract: str
    r1_status: str
    actual_input_status: str
    external_input_required: bool
    current_production_gold_count: int
    required_production_gold_count: int
    current_korean_gold_count: int
    required_korean_gold_count: int
    current_positive_gold_count: int
    current_negative_gold_count: int
    required_positive_gold_count: int
    required_negative_gold_count: int
    current_hard_negative_count: int
    required_hard_negative_count: int
    current_reviewer_count: int   # global engaged(contact evidence)·per-pair coverage 증명 아님.
    reviewer_count_required: int
    reviewer_duplication_required: int
    reviewer_agreement_required: bool
    conflict_adjudication_required: bool
    label_collection_gap: int
    korean_gap: int
    positive_gap: int
    negative_gap: int
    hard_negative_gap: int
    reviewer_gap: int
    calibration_ready: bool
    merge_gate_ready: bool
    next_manual_actions: list[str]
    flags: InternalOpsFlags


class InternalOpsR1PilotBatchStatus(BaseModel):
    """ADR#75 — R1 first reviewer pilot batch freeze + launch readiness(read-only·public truth 아님).

    `r1_reviewer_pilot_batch.run_r1_reviewer_pilot_batch` 의 sanitized r1_pilot_batch_contract 를 미러한다.
    batch frozen 여부·deterministic signature·frozen pair count·expected label files·launch_status·R1 gap·
    R2~R7 No-Go 만 노출한다 — same_event truth·score·rationale·predicted_status·raw PII·secret 은 필드 자체가
    없어 구조적 미노출. **candidate_provenance/pilot_batch_is_production_candidate** 가 합성 fixture 를 production
    후보로 오인하지 못하게 명시(둔갑 0). frozen batch 는 reviewer worklist 동결이지 event truth 가 아니다.
    """
    contract: str
    pilot_batch_id: str
    batch_frozen: bool
    batch_signature: str
    candidate_provenance: str
    pilot_batch_is_production_candidate: bool
    frozen_pair_count: int
    target_pair_count: int
    expected_label_file_count: int
    launch_status: str
    ready_for_manual_launch: bool
    returned_labels_found: bool
    returned_label_count: int
    intake_directory: str
    validation_command: str
    r1_status: str
    production_gold_count: int
    required_production_gold_count: int
    current_r1_gap: int
    r2_r7_no_go: bool
    next_manual_action: str
    flags: InternalOpsFlags


class InternalOpsR1ProductionCandidateStatus(BaseModel):
    """ADR#76 — R1 live production candidate acquisition + dual-track batch readiness(read-only·public truth 아님).

    `r1_production_candidate_acquisition.run_r1_production_candidate_acquisition` 의 sanitized dual-track
    contract 를 미러한다. synthetic dry-run batch 와 live production-candidate batch 를 **명확히 분리**한다 —
    synthetic_dry_run_batch_ready / synthetic_batch_not_production vs production_candidate_batch_ready /
    production_candidate_status(6-state) / candidate_provenance / live_candidate_count. same_event truth·score·
    rationale·predicted_status·raw body·raw PII·secret 은 필드 자체가 없어 구조적 미노출. production-candidate
    batch 도 reviewer worklist 동결이지 same_event 확정이 아니며 production_gold_count 를 늘리지 않는다.
    """
    contract: str
    synthetic_dry_run_batch_ready: bool
    synthetic_batch_not_production: bool
    production_candidate_batch_ready: bool
    production_candidate_status: str
    candidate_provenance: str
    live_call_performed: bool
    live_candidate_count: int
    publishable_pair_count: int
    production_frozen_pair_count: int
    production_batch_id: str
    production_batch_signature: str
    ready_for_manual_launch: bool
    blocked_no_live_production_candidates: bool
    validation_command: str
    intake_directory: str
    r1_status: str
    production_gold_count: int
    required_production_gold_count: int
    current_r1_gap: int
    r2_r7_no_go: bool
    next_manual_action: str
    flags: InternalOpsFlags
