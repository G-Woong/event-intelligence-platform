export interface FinalEventCard {
  id: string;
  title: string;
  summary: string;
  theme: string;
  sectors: string[];
  entities: string[];
  impact_path: string;
  evidence: string[];
  confidence_score: number;
  status: string;
  created_at: string;
}

// ── Event 타임라인 (D-2b) — backend 공개 read 스키마와 1:1 ──
// (backend PublicEvent/PublicEventUpdate/PublicEventTimelineResponse). read-only.
// 내부 식별자(primary_entity_ids·snapshot_card_id·source_refs)는 공개 응답에서 제외되므로 타입에도 없음.
export interface Event {
  id: string;
  canonical_title: string;
  status: string; // active | dormant | closed
  first_seen_at: string;
  last_update_at: string;
  heat: number;
  domains: string[];
  tags: string[];
}

// EventUpdate.evidence 는 write 시 allowlist 키만 sanitize 됨(url/source_type/role/confidence/
// relation/observed_at). 프론트는 이 알려진 키만 렌더(임의 본문/PII 미노출).
export interface EventUpdateEvidence {
  url?: string;
  source_type?: string;
  role?: string;
  confidence?: number;
  relation?: string;
  observed_at?: string;
}

// source_refs(내부 식별자)는 공개 read API 응답에서 제외됨(backend PublicEventUpdate) — 타입에도 없음.
export interface EventUpdate {
  id: string;
  event_id: string;
  observed_at: string;
  delta_summary: string;
  evidence: EventUpdateEvidence[];
  added_domains: string[];
  heat_delta: number;
}

export interface EventTimelineResponse {
  event: Event;
  updates: EventUpdate[];
}

export interface EventSearchHit {
  id: string;
  card_id?: string;
  title: string;
  summary: string | null;
  theme: string | null;
  sectors: string[];
  status?: string | null;
  confidence_score: number | null;
  score: number;
  created_at: string | null;
}

export interface EventSearchResponse {
  total: number;
  hits: EventSearchHit[];
}

export interface Theme {
  id: string;
  name: string;
  label?: string;
  description?: string;
  event_count?: number;
}

export interface Sector {
  id: string;
  name: string;
  label?: string;
  description?: string;
  event_count?: number;
}

export interface HealthResponse {
  status: string;
  version?: string;
  components?: { redis?: string; milvus?: string; postgres?: string; opensearch?: string };
  redis?: string;
  milvus?: string;
  postgres?: string;
}

export interface JobStatus {
  id: string;
  status: string;
  created_at: string;
  updated_at?: string;
  error?: string;
}

// ── ADR#72: internal ops dashboard (InternalOpsPilotExecutionStatus) — backend sanitized contract 와 1:1 ──
// internal-only·read-only·public truth 아님. same_event truth/score/rationale/predicted_status/raw PII 는
// 필드 자체가 없어 구조적 미노출. reviewer pipeline 의 workflow state 만 표현한다.
export interface InternalOpsFlags {
  internal_only: boolean;
  no_public_truth: boolean;
  no_merge: boolean;
  no_public_iu: boolean;
  pii_safe: boolean;
  no_llm: boolean;
  no_db_write: boolean;
  gold_provenance_verified: boolean;
}

export interface InternalOpsPilotExecutionStatus {
  contract: string;
  batch_id: string;
  pilot_status: string;
  execution_status: string;
  contact_evidence_present: boolean;
  real_reviewers_contacted: number;
  returned_label_count: number;
  missing_label_count: number;
  invalid_label_count: number;
  invalid_file_count: number;
  conflict_pair_count: number;
  overdue_count: number;
  production_gold_count: number;
  synthetic_gold_count: number;
  production_gold_provenance_verified: boolean;
  calibration_ready: boolean;
  merge_gate_ready: boolean;
  next_action: string;
  flags: InternalOpsFlags;
}

// ── ADR#73: internal ops auth/deploy preflight + R1~R7 readiness — backend sanitized contract 와 1:1 ──
// admin token **값**은 필드 자체가 없고 admin_token_configured(존재 여부)만. public truth 아님·read-only.
export interface InternalOpsReadinessStage {
  stage: string;
  goal: string;
  current_status: string;
  blocker: string;
  next_action: string;
}

export interface InternalOpsPreflightStatus {
  contract: string;
  preflight_status: string;
  auth_boundary_status: string;
  app_env: string;
  admin_token_required: boolean;
  admin_token_configured: boolean;
  feature_flag_required: boolean;
  feature_flag_enabled: boolean;
  frontend_server_env_required: boolean;
  public_nav_exposed: boolean;
  deployment_proven: boolean;
  actual_input_status: string;
  external_input_required: boolean;
  production_gold_count: number;
  calibration_ready: boolean;
  merge_gate_ready: boolean;
  r1_r7_readiness_matrix_ready: boolean;
  r1_r7_stages: InternalOpsReadinessStage[];
  flags: InternalOpsFlags;
  block_reasons: string[];
  next_actions: string[];
}

// ── ADR#74: R1 production gold acquisition operating plan — backend sanitized contract 와 1:1 ──
// R1 status(4-state)·gold floor current/required·gap·reviewer 요구·operator next manual action 만. public truth
// 아님·read-only. target floor 는 operating floor 이지 production truth 아님(R1 satisfied 는 calibration_ready 일 때만).
export interface InternalOpsR1AcquisitionStatus {
  contract: string;
  r1_status: string;
  actual_input_status: string;
  external_input_required: boolean;
  current_production_gold_count: number;
  required_production_gold_count: number;
  current_korean_gold_count: number;
  required_korean_gold_count: number;
  current_positive_gold_count: number;
  current_negative_gold_count: number;
  required_positive_gold_count: number;
  required_negative_gold_count: number;
  current_hard_negative_count: number;
  required_hard_negative_count: number;
  current_reviewer_count: number; // global engaged(contact evidence)·per-pair coverage 아님.
  reviewer_count_required: number;
  reviewer_duplication_required: number;
  reviewer_agreement_required: boolean;
  conflict_adjudication_required: boolean;
  label_collection_gap: number;
  korean_gap: number;
  positive_gap: number;
  negative_gap: number;
  hard_negative_gap: number;
  reviewer_gap: number;
  calibration_ready: boolean;
  merge_gate_ready: boolean;
  next_manual_actions: string[];
  flags: InternalOpsFlags;
}

// ── ADR#75: R1 first reviewer pilot batch freeze + launch readiness — backend sanitized contract 와 1:1 ──
// batch frozen 여부·deterministic signature·frozen pair count·expected files·launch_status·R1 gap·R2~R7 No-Go 만.
// candidate_provenance/pilot_batch_is_production_candidate 가 합성 fixture 를 production 후보로 오인 차단(둔갑 0).
// frozen batch 는 reviewer worklist 동결이지 event truth 가 아니다. public truth 아님·read-only.
export interface InternalOpsR1PilotBatchStatus {
  contract: string;
  pilot_batch_id: string;
  batch_frozen: boolean;
  batch_signature: string;
  candidate_provenance: string;
  pilot_batch_is_production_candidate: boolean;
  frozen_pair_count: number;
  target_pair_count: number;
  expected_label_file_count: number;
  launch_status: string;
  ready_for_manual_launch: boolean;
  returned_labels_found: boolean;
  returned_label_count: number;
  intake_directory: string;
  validation_command: string;
  r1_status: string;
  production_gold_count: number;
  required_production_gold_count: number;
  current_r1_gap: number;
  r2_r7_no_go: boolean;
  next_manual_action: string;
  flags: InternalOpsFlags;
}

// ADR#76 — R1 live production candidate acquisition + dual-track batch readiness(read-only·public truth 아님).
// synthetic dry-run batch 와 live production-candidate batch 를 분리 표시. same_event truth·score·rationale·
// predicted_status·raw body·PII·secret 은 필드 자체가 없다(구조적 미노출).
export interface InternalOpsR1ProductionCandidateStatus {
  contract: string;
  synthetic_dry_run_batch_ready: boolean;
  synthetic_batch_not_production: boolean;
  production_candidate_batch_ready: boolean;
  production_candidate_status: string;
  candidate_provenance: string;
  live_call_performed: boolean;
  live_candidate_count: number;
  publishable_pair_count: number;
  production_frozen_pair_count: number;
  production_batch_id: string;
  production_batch_signature: string;
  ready_for_manual_launch: boolean;
  blocked_no_live_production_candidates: boolean;
  validation_command: string;
  intake_directory: string;
  r1_status: string;
  production_gold_count: number;
  required_production_gold_count: number;
  current_r1_gap: number;
  r2_r7_no_go: boolean;
  next_manual_action: string;
  flags: InternalOpsFlags;
}

// ── ADR#78: near-match gap diagnostic + targeted acquisition frontier — backend sanitized contract 와 1:1 ──
// near-match gap status·원인 가설들(양가·단정 아님)·confidence·targeted seed/live attempt·provider/Korean readiness·
// production candidate status·R1 gap·R2~R7 No-Go·필수 정직 copy 만. same_event truth·score·rationale·predicted_status·
// raw body·raw PII·secret 필드 자체가 없음. read API 는 live 0(near_match_gap_status=insufficient_debug_artifact 정상).
// near-match 0 은 같은 사건 부재를 증명하지 않는다(required_copy 가 명시). public truth 아님·read-only.
export interface AcquisitionRootCauseHypothesis {
  cause: string;
  signal: string;
}

export interface AcquisitionFrontierFlags {
  no_public_truth: boolean;
  no_same_event_truth: boolean;
  no_score: boolean;
  no_rationale: boolean;
  no_predicted_status: boolean;
  no_raw_body: boolean;
  no_secret: boolean;
}

export interface InternalOpsAcquisitionFrontierStatus {
  contract: string;
  near_match_gap_status: string;
  root_cause_hypotheses: AcquisitionRootCauseHypothesis[];
  root_cause_confidence: string;
  targeted_query_seed_count: number;
  live_attempt_count: number;
  live_candidate_count: number;
  publishable_pair_count: number;
  production_candidate_status: string;
  production_candidate_batch_ready: boolean;
  candidate_provenance: string;
  provider_expansion_plan_ready: boolean;
  korean_source_strategy_ready: boolean;
  blocked_reason: string;
  current_r1_gap: number;
  production_gold_count: number;
  r2_r7_no_go: boolean;
  required_copy: string[];
  flags: AcquisitionFrontierFlags;
}
