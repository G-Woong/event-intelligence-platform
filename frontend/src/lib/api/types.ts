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

// ADR#79 — discrete-event acquisition + deterministic recall probe frontier(read-only·public truth 아님).
// r1_discrete_event_acquisition 의 sanitized internal_ops_discrete_acquisition_frontier 미러. recall probe lift 는
// reviewer 라우팅 신호이지 same-event 단정 아님(merge 미적용). same_event truth·per-pair score·rationale·
// predicted_status·raw body·PII·secret 은 필드 자체가 없어 구조적 미노출.
export interface InternalOpsDiscreteAcquisitionFrontier {
  contract: string;
  discrete_event_seed_selected: string | null;
  discrete_event_seed_source: string | null;
  discrete_event_time_window: string | null;
  discrete_seed_valid_count: number;
  near_match_gap_status: string;
  root_cause_hypotheses: AcquisitionRootCauseHypothesis[];
  root_cause_confidence: string;
  max_recall_probe_score: number;
  recall_probe_pairs_newly_routed: number;
  recall_probe_applies_to_merge: boolean;
  recall_probe_lever_demonstrated: boolean;
  // ADR#80 — recall probe applied to ACTUAL live cross-source pairs (aggregate only; per-pair score not exposed).
  max_live_recall_probe_score: number;
  live_pairs_newly_routed_by_probe: number;
  live_recall_lift_status: string; // live_recall_lift_found / live_no_recall_lift / live_blocked_by_rate_or_opt_in
  live_frontier_verdict: string;
  live_candidate_count: number;
  production_candidate_status: string;
  blocked_reason: string;
  provider_breadth_next_action: string;
  korean_source_next_action: string;
  current_r1_gap: number;
  production_gold_count: number;
  r2_r7_no_go: boolean;
  required_copy: string[];
  flags: AcquisitionFrontierFlags;
}

// ADR#81 — provider breadth + named single-event seed + KO source path frontier(read-only·public truth 아님).
// r1_provider_breadth_acquisition 의 sanitized internal_ops_provider_breadth_frontier 미러. provider breadth 는
// acquisition support 이지 truth 아님·named seed 는 candidate generation 이지 same-event proof 아님·community 는
// event anchor 아님. same_event truth·per-pair score·rationale·predicted_status·raw body·PII·secret 은 필드 자체가
// 없어 구조적 미노출.
export interface InternalOpsProviderBreadthFrontier {
  contract: string;
  // provider breadth(§10).
  provider_breadth_status: string;
  provider_breadth_inventory_ready: boolean;
  query_capable_provider_count: number;
  feed_only_provider_count: number;
  official_source_count: number;
  search_url_candidate_count: number;
  ko_official_news_count: number;
  community_reaction_only_count: number;
  market_signal_only_count: number;
  catalog_enrichment_only_count: number;
  unknown_quarantine_count: number;
  anchor_eligible_count: number;
  // named single-event seed(§10).
  named_seed_bank_status: string;
  named_seed_count: number;
  selected_seed_for_next_live_run: string | null;
  seed_type: string;
  // KO source path(§10).
  ko_source_path_status: string;
  ko_tokenization_risk_recorded: boolean;
  // live recall(shared·aggregate only·per-pair score not exposed).
  latest_live_seed: string | null;
  live_recall_lift_status: string;
  max_live_recall_probe_score: number;
  newly_routed_count: number;
  // production / gap(shared).
  production_candidate_status: string;
  blocked_reason: string;
  current_r1_gap: number;
  r2_r7_no_go: boolean;
  // next action + copy.
  acquisition_next_action: string;
  required_copy: string[];
  flags: AcquisitionFrontierFlags;
}

// ADR#82 — bounded live breadth run + named-event date-pin gate + production-candidate freeze attempt frontier
// (read-only·public truth 아님). r1_bounded_live_breadth_run 의 sanitized internal_ops_bounded_live_breadth_frontier
// 미러. provider breadth 는 acquisition support 이지 truth 아님·bounded live run 은 operator 확인 date-pinned event
// 요구·production candidate freeze 는 reviewer worklist 이지 same-event truth 아님. same_event truth·per-pair score·
// rationale·predicted_status·raw body·PII·secret 은 필드 자체가 없어 구조적 미노출.
export interface InternalOpsBoundedLiveBreadthFrontier {
  contract: string;
  latest_bounded_live_run_status: string;
  // named seed date-pin(§5).
  named_seed_selected: string | null;
  named_seed_date_pin_status: string;
  selected_seed_actual_occurrence: string | null;
  // bounded live(§6·§7).
  live_query_approved: boolean;
  live_query_executed: boolean;
  live_call_count: number;
  providers_used: string[];
  provider_breadth_used: number;
  key_free_provider_count: number;
  credential_required_provider_count: number;
  comparison_pair_count: number;
  max_recall_probe_score: number;
  newly_routed_count: number;
  // production candidate freeze(§7).
  production_candidate_status: string;
  production_candidate_batch_ready: boolean;
  production_frozen_pair_count: number;
  sanitized_snapshot_status: string;
  // KO source lane(§8).
  ko_source_lane_status: string;
  ko_named_seed_needed: boolean;
  ko_floor_current: number;
  ko_floor_required: number;
  // gap / next action + copy.
  blocked_reason: string;
  acquisition_next_action: string;
  current_r1_gap: number;
  production_gold_count: number;
  r2_r7_no_go: boolean;
  required_copy: string[];
  flags: AcquisitionFrontierFlags;
}

// ADR#83 — date-pinned live query plumbing + bounded live run + production-candidate freeze frontier.
// `r1_bounded_live_breadth_run.build_date_pinned_live_run_frontier` 의 sanitized 미러(public truth 아님).
// same_event truth·per-pair score·rationale·predicted_status·raw body·PII·secret·named_entity/event_phrase 전문은
// 필드 자체가 없어 구조적 미노출. operator_event_provided bool + occurrence_date(operator 주장) 만 노출.
export interface InternalOpsDatePinnedLiveRunFrontier {
  contract: string;
  latest_date_pinned_live_run_status: string;
  // operator event / date-pin(§B·§5·§6).
  operator_event_provided: boolean;
  occurrence_date: string | null;
  occurrence_date_valid_iso: boolean;
  date_pinned_named_event_valid: boolean;
  live_query_target_wired: boolean;
  // bounded live(§6·§7).
  live_query_approved: boolean;
  live_query_executed: boolean;
  live_call_count: number;
  providers_used: string[];
  comparison_pair_count: number;
  max_recall_probe_score: number;
  newly_routed_count: number;
  // production candidate freeze(§7·§8).
  production_candidate_status: string;
  production_candidate_batch_ready: boolean;
  production_frozen_pair_count: number;
  candidate_provenance: string;
  sanitized_snapshot_status: string;
  // ADR#84: provider out-of-window record drop 강제 + freeze→contact 직전 handoff readiness(freeze 없으면 false).
  date_window_enforced: boolean;
  reviewer_handoff_ready: boolean;
  // ADR#85: date-window fidelity control experiment(메커니즘은 confidence 와 함께·단정 0) + window-honoring readiness.
  provider_date_window_fidelity_status: string;
  control_experiment_status: string;
  date_filter_mechanism_primary: string;
  date_filter_mechanism_confidence: string;
  out_of_window_records_dropped: number;
  window_honoring_source_status: string;
  // ADR#86: Federal Register window-honoring adapter(key-free·official) + official×news role-bridge.
  // FR=official 증거(news 아님)·bridge=reviewer-routing only·official 단독 freeze 금지·date_filter live 검증.
  federal_register_adapter_status: string;
  federal_register_live_status: string;
  federal_register_date_filter_capability: string;
  official_news_bridge_status: string;
  official_records_count: number;
  news_records_count: number;
  bridge_candidate_count: number;
  official_news_freeze_eligible_count: number;
  // ADR#87: regulatory seed bank(official×news 동시 포착 가능 event shape) + official×news live acquisition status.
  // live status=fetch→bridge→freeze 분류·handoff=freeze→contact-PRE(전송 0)·official 단독 candidate 금지.
  regulatory_seed_bank_status: string;
  selected_regulatory_seed_id: string | null;
  official_news_live_status: string;
  official_news_production_candidate_status: string;
  official_news_reviewer_handoff_ready: boolean;
  // ADR#88: operator-confirmed event intake + reviewer contact readiness + official×news label intake readiness.
  // operator confirmation=live regulatory acquisition 전 게이트(truth 아님)·contact readiness ≠ actual sending·
  // label intake readiness=synthetic dry-run(production gold 0).
  operator_event_status: string;
  operator_confirmed: boolean;
  confirmation_valid: boolean;
  confirmation_blocked_reason: string;
  reviewer_contact_ready: boolean;
  label_intake_readiness_status: string;
  // ADR#89: operator payload entrypoint + returned label dropbox readiness + reviewer contact launch checklist.
  // operator payload=real(gitignored)/example(committed) 분리·live-run gate; dropbox=수신 경로/schema(실 returned label
  // 전까지 production gold 0); contact launch checklist=수동 접촉 직전(actual sending 0).
  operator_payload_status: string;
  operator_payload_path_status: string;
  label_dropbox_ready: boolean;
  actual_returned_label_count: number;
  reviewer_contact_checklist_ready: boolean;
  // ADR#90 product-vision contracts(payload authoring next action + live no-yield taxonomy + hot intelligence post /
  // agent hotness / community interaction gate). 전부 runtime-disabled contract — public post·comment auto-reply 는
  // R1/R2·MERGE_GATE·public-IU gate 전 No-Go. community-style intelligence post 방향 정렬.
  operator_payload_template_ready: boolean;
  operator_payload_next_action: string;
  live_no_yield_taxonomy_status: string;
  hot_intelligence_post_contract_status: string;
  agent_hotness_contract_status: string;
  community_interaction_gate_status: string;
  // KO source lane(§8).
  ko_source_lane_status: string;
  ko_named_seed_needed: boolean;
  ko_floor_current: number;
  ko_floor_required: number;
  // gap / next action + copy.
  blocked_reason: string;
  acquisition_next_action: string;
  current_r1_gap: number;
  production_gold_count: number;
  r2_r7_no_go: boolean;
  required_copy: string[];
  flags: AcquisitionFrontierFlags;
}
