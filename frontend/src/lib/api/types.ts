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
