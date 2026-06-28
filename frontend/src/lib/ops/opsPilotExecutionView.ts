// ADR#72 — internal ops dashboard 표시용 순수 view/sanitize helper(public truth 아님·read-only).
//
// backend 가 sanitized `InternalOpsPilotExecutionStatus` 만 내려주지만, UI 가 실수로 forbidden 필드를
// re-introduce 하지 못하게 한 겹 더 막는다(R-OpsUIPrematureTruth·심층 방어). same_event truth·semantic score·
// model rationale·predicted_status·reviewer raw PII 는 표시 대상이 아니다 — 발견 시 fail-loud.
import type {
  InternalOpsAcquisitionFrontierStatus,
  InternalOpsBoundedLiveBreadthFrontier,
  InternalOpsDatePinnedLiveRunFrontier,
  InternalOpsDiscreteAcquisitionFrontier,
  InternalOpsPilotExecutionStatus,
  InternalOpsPreflightStatus,
  InternalOpsProviderBreadthFrontier,
  InternalOpsR1AcquisitionStatus,
  InternalOpsR1PilotBatchStatus,
  InternalOpsR1ProductionCandidateStatus,
} from "@/lib/api/types";

// internal ops dashboard 가 절대 표시하면 안 되는 키(있으면 오염). recursive 검사.
// backend `_HANDOFF_FORBIDDEN_KEYS` 와 동기화(ADR#73·둘 다 defense-in-depth·primary 가드는 서버측 `_assert_pii_safe`).
export const FORBIDDEN_OPS_FIELDS: readonly string[] = [
  "score",
  "model_score",
  "rationale",
  "predicted_status",
  "same_event",
  "raw_body",
  "body",
  "reviewer_name",
  "name",
  "reviewer_email",
  "reviewer_phone",
  "email",
  "phone",
  "secret",
  "api_key",
  "provider_secret",
  "hidden_rank",
  "source_hidden_rank",
];

// 필수 no-go copy(UI 가 truth/merge/public product 로 오인되지 않게 prominently 표시).
export const OPS_NO_GO_COPY = {
  heading: "Internal operations status",
  notPublicTruth: "Not public truth",
  noMerge: "No merge allowed",
  goldUnverified: "Gold not verified yet",
  awaitingReturn: "Awaiting reviewer return",
  requiresMergeGate: "Requires MERGE_GATE before public IU",
} as const;

// contract 어떤 depth 에도 forbidden 키가 없음을 강제(있으면 throw — 렌더 차단).
export function assertOpsContractSafe(contract: unknown): void {
  const walk = (o: unknown): void => {
    if (Array.isArray(o)) {
      o.forEach(walk);
      return;
    }
    if (o && typeof o === "object") {
      for (const [k, v] of Object.entries(o as Record<string, unknown>)) {
        if (FORBIDDEN_OPS_FIELDS.includes(k)) {
          throw new Error(`internal ops contract leaked forbidden field: ${k}`);
        }
        walk(v);
      }
    }
  };
  walk(contract);
}

export interface OpsDisplayRow {
  label: string;
  value: string;
}

// contract → read-only 표시 행(workflow state 만). production gold 는 "unverified" 라벨 동반.
export function toOpsDisplayRows(c: InternalOpsPilotExecutionStatus): OpsDisplayRow[] {
  return [
    { label: "Execution status", value: c.execution_status },
    { label: "Pilot status", value: c.pilot_status },
    { label: "Contacted reviewers", value: String(c.real_reviewers_contacted) },
    { label: "Returned labels", value: `${c.returned_label_count}` },
    { label: "Missing labels", value: `${c.missing_label_count}` },
    { label: "Invalid labels", value: `${c.invalid_label_count}` },
    { label: "Conflicts", value: `${c.conflict_pair_count}` },
    { label: "Overdue", value: `${c.overdue_count}` },
    { label: "Production gold (unverified)", value: `${c.production_gold_count}` },
    { label: "Calibration ready", value: String(c.calibration_ready) },
    { label: "Merge gate ready", value: String(c.merge_gate_ready) },
    { label: "Next action", value: c.next_action },
  ];
}

// ── ADR#73 preflight(auth/deploy posture + R1~R7 readiness) view helpers ───────────────────────────────
// admin token **값**은 표시하지 않는다(admin_token_configured 존재 여부 bool 만). public truth 아님.
export const OPS_PREFLIGHT_COPY = {
  externalInputRequired: "Awaiting actual returned labels — external reviewer input required",
  unsafeExposure: "UNSAFE: dashboard enabled without auth in a non-production environment",
  misconfigured: "Misconfigured: dashboard enabled without admin token in a prod-like environment",
  deploymentUnproven: "Deployment boundary not proven (per-user auth absent — internal only)",
} as const;

// posture/actual-input → read-only 표시 행(secret 0·workflow state 만).
export function toPreflightDisplayRows(p: InternalOpsPreflightStatus): OpsDisplayRow[] {
  return [
    { label: "Preflight status", value: p.preflight_status },
    { label: "Auth boundary", value: p.auth_boundary_status },
    { label: "App env", value: p.app_env },
    { label: "Admin token configured", value: String(p.admin_token_configured) },
    { label: "Dashboard flag enabled", value: String(p.feature_flag_enabled) },
    { label: "Deployment proven", value: String(p.deployment_proven) },
    { label: "Actual input status", value: p.actual_input_status },
    { label: "External input required", value: String(p.external_input_required) },
    { label: "Production gold (unverified)", value: `${p.production_gold_count}` },
    { label: "Merge gate ready", value: String(p.merge_gate_ready) },
  ];
}

// posture/actual-input → operator 가 봐야 할 경고 배너(무인증 노출·오설정·외부 입력 필요·배포 미증명).
export function preflightWarnings(p: InternalOpsPreflightStatus): string[] {
  const out: string[] = [];
  if (p.preflight_status === "unsafe_public_exposure") out.push(OPS_PREFLIGHT_COPY.unsafeExposure);
  if (p.preflight_status === "misconfigured") out.push(OPS_PREFLIGHT_COPY.misconfigured);
  if (p.external_input_required) out.push(OPS_PREFLIGHT_COPY.externalInputRequired);
  if (!p.deployment_proven) out.push(OPS_PREFLIGHT_COPY.deploymentUnproven);
  return out;
}

// ── ADR#74 R1 gold acquisition(gap + operator next action) view helpers ─────────────────────────────────
// 필수 copy(§6) — R1 gap/No-Go ladder 를 operator 가 명확히 보게(public truth 아님). target floor 는 operating
// floor 이지 production truth 가 아니다.
export const OPS_R1_COPY = {
  blockedByLabels: "R1 is blocked by actual returned labels",
  goldZeroUntilImport: "Gold count is 0 until human production labels are imported",
  laddersNoGo: "R2~R7 remain No-Go",
  internalOnly: "Internal operations only",
  notPublicTruth: "Not public truth",
} as const;

// R1 status → current/required + gap 표시 행(read-only·workflow gap 만). production gold 는 "unverified" 라벨 동반.
export function toR1DisplayRows(r: InternalOpsR1AcquisitionStatus): OpsDisplayRow[] {
  const cr = (cur: number, req: number, gap: number) => `${cur} / ${req} (gap ${gap})`;
  return [
    { label: "R1 status", value: r.r1_status },
    { label: "Actual input status", value: r.actual_input_status },
    { label: "Production gold (unverified)", value: cr(r.current_production_gold_count, r.required_production_gold_count, r.label_collection_gap) },
    { label: "Korean gold", value: cr(r.current_korean_gold_count, r.required_korean_gold_count, r.korean_gap) },
    { label: "Positive gold", value: cr(r.current_positive_gold_count, r.required_positive_gold_count, r.positive_gap) },
    { label: "Negative gold", value: cr(r.current_negative_gold_count, r.required_negative_gold_count, r.negative_gap) },
    { label: "Hard-negative gold", value: cr(r.current_hard_negative_count, r.required_hard_negative_count, r.hard_negative_gap) },
    // global engaged(contact evidence)·per-pair coverage 주장 아님(adversarial #10) — current/required/gap 명시.
    { label: "Reviewers engaged (>=2 required)", value: cr(r.current_reviewer_count, r.reviewer_count_required, r.reviewer_gap) },
    { label: "Reviewer agreement required", value: String(r.reviewer_agreement_required) },
    { label: "Conflict adjudication required", value: String(r.conflict_adjudication_required) },
    { label: "Calibration ready", value: String(r.calibration_ready) },
    { label: "Merge gate ready", value: String(r.merge_gate_ready) },
  ];
}

// R1 status → operator 가 봐야 할 경고 배너(라벨 차단·gold 0·R2~R7 No-Go·외부 입력 필요).
export function r1Warnings(r: InternalOpsR1AcquisitionStatus): string[] {
  const out: string[] = [];
  if (r.r1_status === "blocked_no_labels") out.push(OPS_R1_COPY.blockedByLabels);
  if (r.current_production_gold_count === 0) out.push(OPS_R1_COPY.goldZeroUntilImport);
  if (!r.merge_gate_ready) out.push(OPS_R1_COPY.laddersNoGo);
  return out;
}

// ── ADR#75 R1 pilot batch freeze + launch readiness view helpers ────────────────────────────────────────
// 필수 copy(§7) — frozen batch 가 truth/production 으로 오인되지 않게(public truth 아님). frozen batch 는
// reviewer worklist 동결이지 event truth 가 아니며, 합성 fixture 라 production gold 0 유지.
export const OPS_R1_BATCH_COPY = {
  worklistNotTruth: "Frozen batch is a reviewer worklist, not truth",
  manualLaunchRequired: "Manual launch required",
  returnedLabelsMissing: "Returned labels are still missing",
  goldZeroUntilImport: "Production gold remains 0 until human labels are imported",
  laddersNoGo: "R2~R7 remain No-Go",
  syntheticFixture: "Synthetic fixture pilot — production candidates require live source overlap",
} as const;

// pilot batch → launch readiness 표시 행(read-only·workflow state 만). production gold 는 "unverified" 라벨 동반.
export function toR1BatchDisplayRows(b: InternalOpsR1PilotBatchStatus): OpsDisplayRow[] {
  return [
    { label: "Pilot batch id", value: b.pilot_batch_id },
    { label: "Launch status", value: b.launch_status },
    { label: "Batch frozen", value: String(b.batch_frozen) },
    { label: "Candidate provenance", value: b.candidate_provenance },
    { label: "Production candidate", value: String(b.pilot_batch_is_production_candidate) },
    { label: "Frozen pairs (pilot_n)", value: `${b.frozen_pair_count} / ${b.target_pair_count}` },
    { label: "Expected label files", value: `${b.expected_label_file_count}` },
    { label: "Ready for manual launch", value: String(b.ready_for_manual_launch) },
    { label: "Returned labels found", value: String(b.returned_labels_found) },
    { label: "Batch signature", value: b.batch_signature },
    { label: "Production gold (unverified)", value: `${b.production_gold_count} / ${b.required_production_gold_count} (gap ${b.current_r1_gap})` },
    { label: "R1 status", value: b.r1_status },
    { label: "R2~R7 No-Go", value: String(b.r2_r7_no_go) },
  ];
}

// pilot batch → operator 가 봐야 할 경고 배너(worklist≠truth·수동 실행·라벨 미회수·gold 0·R2~R7 No-Go·합성 fixture).
export function r1BatchWarnings(b: InternalOpsR1PilotBatchStatus): string[] {
  const out: string[] = [OPS_R1_BATCH_COPY.worklistNotTruth];
  if (b.ready_for_manual_launch) out.push(OPS_R1_BATCH_COPY.manualLaunchRequired);
  if (!b.returned_labels_found) out.push(OPS_R1_BATCH_COPY.returnedLabelsMissing);
  if (b.production_gold_count === 0) out.push(OPS_R1_BATCH_COPY.goldZeroUntilImport);
  if (b.r2_r7_no_go) out.push(OPS_R1_BATCH_COPY.laddersNoGo);
  if (!b.pilot_batch_is_production_candidate) out.push(OPS_R1_BATCH_COPY.syntheticFixture);
  return out;
}

// ── ADR#76 R1 live production candidate acquisition + dual-track view helpers ───────────────────────────
// 필수 copy(§7) — synthetic dry-run batch 와 live production-candidate batch 를 명확히 분리(둔갑 0). production
// candidate 도 truth 가 아니며, live-derived publishable pair 없이는 production batch 가 ready 되지 않는다.
export const OPS_R1_PROD_COPY = {
  syntheticNotProduction: "Synthetic dry-run batch is not production",
  requiresLivePairs: "Production candidate batch requires live-derived publishable pairs",
  worklistNotTruth: "Candidate worklist is not truth",
  returnedLabelsRequired: "Returned human labels are still required",
  goldZeroUntilImport: "Production gold remains 0 until human labels are imported",
  laddersNoGo: "R2~R7 remain No-Go",
} as const;

// production candidate acquisition → dual-track 표시 행(read-only·workflow state 만·둔갑 0).
export function toR1ProdCandidateDisplayRows(
  p: InternalOpsR1ProductionCandidateStatus,
): OpsDisplayRow[] {
  return [
    { label: "Production candidate status", value: p.production_candidate_status },
    { label: "Synthetic dry-run batch ready", value: String(p.synthetic_dry_run_batch_ready) },
    { label: "Synthetic batch is non-production", value: String(p.synthetic_batch_not_production) },
    { label: "Production candidate batch ready", value: String(p.production_candidate_batch_ready) },
    { label: "Candidate provenance", value: p.candidate_provenance },
    { label: "Live call performed", value: String(p.live_call_performed) },
    { label: "Live candidate pairs", value: `${p.live_candidate_count}` },
    { label: "Publishable pairs", value: `${p.publishable_pair_count}` },
    { label: "Production frozen pairs (pilot_n)", value: `${p.production_frozen_pair_count} / ${p.required_production_gold_count}` },
    { label: "Ready for manual launch", value: String(p.ready_for_manual_launch) },
    { label: "Blocked: no live production candidates", value: String(p.blocked_no_live_production_candidates) },
    { label: "Production gold (unverified)", value: `${p.production_gold_count} / ${p.required_production_gold_count} (gap ${p.current_r1_gap})` },
    { label: "R1 status", value: p.r1_status },
    { label: "R2~R7 No-Go", value: String(p.r2_r7_no_go) },
  ];
}

// production candidate acquisition → operator 경고 배너(synthetic≠production·live pair 필요·worklist≠truth·라벨 필요·gold 0·No-Go).
export function r1ProdCandidateWarnings(
  p: InternalOpsR1ProductionCandidateStatus,
): string[] {
  const out: string[] = [OPS_R1_PROD_COPY.syntheticNotProduction, OPS_R1_PROD_COPY.worklistNotTruth];
  if (!p.production_candidate_batch_ready) out.push(OPS_R1_PROD_COPY.requiresLivePairs);
  if (p.production_gold_count === 0) out.push(OPS_R1_PROD_COPY.returnedLabelsRequired);
  if (p.production_gold_count === 0) out.push(OPS_R1_PROD_COPY.goldZeroUntilImport);
  if (p.r2_r7_no_go) out.push(OPS_R1_PROD_COPY.laddersNoGo);
  return out;
}

// ── ADR#78 near-match gap diagnostic + targeted acquisition frontier view helpers ───────────────────────
// 필수 copy(§11) — near-match 0 이 같은 사건 부재를 증명하지 않으며 원인이 미확정임을 operator 가 명확히 보게.
// 원인 가설은 양가(단정 아님)로 표시하고, production candidate=reviewer worklist≠truth·gold 0·R2~R7 No-Go 를 강제.
export const OPS_FRONTIER_COPY = {
  zeroNotProof: "Near-match 0 does not prove no same event",
  causeUnresolved: "Cause unresolved: detector miss vs different-events vs provider narrowness",
  requiresLivePair: "Production candidate requires live-derived publishable pair",
  worklistNotTruth: "Production candidate is reviewer worklist, not truth",
  goldZeroUntilLabels: "R1 gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
} as const;

// frontier → read-only 표시 행(near-match gap·원인 가설·acquisition 상태만; score/rationale/same_event 0).
export function toR1FrontierDisplayRows(
  f: InternalOpsAcquisitionFrontierStatus,
): OpsDisplayRow[] {
  const hyp = f.root_cause_hypotheses
    .filter((h) => h.signal === "supporting" || h.signal === "plausible")
    .map((h) => `${h.cause} [${h.signal}]`)
    .join("; ");
  return [
    { label: "Near-match gap status", value: f.near_match_gap_status },
    { label: "Root-cause confidence", value: f.root_cause_confidence },
    { label: "Root-cause hypotheses (not asserted)", value: hyp || "(none)" },
    { label: "Targeted query seeds", value: `${f.targeted_query_seed_count}` },
    { label: "Live attempts", value: `${f.live_attempt_count}` },
    { label: "Live candidate pairs (comparison, not match)", value: `${f.live_candidate_count}` },
    { label: "Publishable near-match pairs", value: `${f.publishable_pair_count}` },
    { label: "Production candidate status", value: f.production_candidate_status },
    { label: "Production candidate batch ready", value: String(f.production_candidate_batch_ready) },
    { label: "Candidate provenance", value: f.candidate_provenance },
    { label: "Provider expansion plan ready", value: String(f.provider_expansion_plan_ready) },
    { label: "Korean source strategy ready", value: String(f.korean_source_strategy_ready) },
    { label: "Blocked reason", value: f.blocked_reason || "(none)" },
    { label: "Production gold (unverified)", value: `${f.production_gold_count} (gap ${f.current_r1_gap})` },
    { label: "R2~R7 No-Go", value: String(f.r2_r7_no_go) },
  ];
}

// frontier → operator 경고 배너(near-match 0 ≠ 증명·원인 미확정·live pair 필요·worklist≠truth·gold 0·No-Go).
// backend required_copy(§11) 를 우선 표시하고, 누락 시 로컬 상수로 보강(defense-in-depth).
export function r1FrontierWarnings(
  f: InternalOpsAcquisitionFrontierStatus,
): string[] {
  const out: string[] = [...(f.required_copy ?? [])];
  const ensure = (s: string) => {
    if (!out.includes(s)) out.push(s);
  };
  ensure(OPS_FRONTIER_COPY.zeroNotProof);
  ensure(OPS_FRONTIER_COPY.causeUnresolved);
  ensure(OPS_FRONTIER_COPY.worklistNotTruth);
  if (!f.production_candidate_batch_ready) ensure(OPS_FRONTIER_COPY.requiresLivePair);
  if (f.production_gold_count === 0) ensure(OPS_FRONTIER_COPY.goldZeroUntilLabels);
  if (f.r2_r7_no_go) ensure(OPS_FRONTIER_COPY.laddersNoGo);
  return out;
}

// ── ADR#79 discrete-event acquisition + deterministic recall probe frontier view helpers ────────────────
// 필수 copy(§9) — recall probe lift 는 reviewer 라우팅 신호이지 same-event 단정이 아님(merge 미적용)을 operator 가
// 명확히 보게. discrete seed=수집 의도(shape)·near-match 0≠증명·gold 0·R2~R7 No-Go 를 강제.
export const OPS_DISCRETE_COPY = {
  recallProbeRoutingOnly: "Recall probe is reviewer-routing only, not merge",
  liftNotSameEvent: "Recall probe lift on synthetic does not assert same-event on live frontier",
  newlyRoutedNotSameEvent: "Newly routed does not mean same event", // ADR#80 §7 required copy.
  productionGoldZero: "Production gold remains 0 until human labels are returned", // ADR#80 §7 required copy.
  zeroNotProof: "Near-match 0 does not prove no same event",
  worklistNotTruth: "Production candidate is reviewer worklist, not truth",
  goldZeroUntilLabels: "R1 gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
} as const;

// discrete frontier → read-only 표시 행(discrete seed·near-match gap·recall probe lift 신호만; per-pair score/same_event 0).
export function toR1DiscreteFrontierDisplayRows(
  f: InternalOpsDiscreteAcquisitionFrontier,
): OpsDisplayRow[] {
  const hyp = f.root_cause_hypotheses
    .filter((h) => h.signal === "supporting" || h.signal === "plausible")
    .map((h) => `${h.cause} [${h.signal}]`)
    .join("; ");
  return [
    { label: "Discrete event seed", value: f.discrete_event_seed_selected ?? "(none)" },
    { label: "Seed source", value: f.discrete_event_seed_source ?? "(none)" },
    { label: "Time window", value: f.discrete_event_time_window ?? "(none)" },
    { label: "Valid discrete seeds", value: `${f.discrete_seed_valid_count}` },
    { label: "Near-match gap status", value: f.near_match_gap_status },
    { label: "Root-cause confidence", value: f.root_cause_confidence },
    { label: "Root-cause hypotheses (not asserted)", value: hyp || "(none)" },
    { label: "Recall probe max score (routing signal, not truth)", value: `${f.max_recall_probe_score}` },
    { label: "Recall probe pairs newly routed", value: `${f.recall_probe_pairs_newly_routed}` },
    { label: "Recall probe applies to merge", value: String(f.recall_probe_applies_to_merge) },
    { label: "Recall probe lever demonstrated (synthetic)", value: String(f.recall_probe_lever_demonstrated) },
    { label: "Live recall lift status", value: f.live_recall_lift_status },
    { label: "Live recall probe max score (routing signal, not truth)", value: `${f.max_live_recall_probe_score}` },
    { label: "Live pairs newly routed by probe (not same-event)", value: `${f.live_pairs_newly_routed_by_probe}` },
    { label: "Live candidate pairs (comparison, not match)", value: `${f.live_candidate_count}` },
    { label: "Production candidate status", value: f.production_candidate_status },
    { label: "Blocked reason", value: f.blocked_reason || "(none)" },
    { label: "Provider breadth next action", value: f.provider_breadth_next_action },
    { label: "Korean source next action", value: f.korean_source_next_action },
    { label: "Production gold (unverified)", value: `${f.production_gold_count} (gap ${f.current_r1_gap})` },
    { label: "R2~R7 No-Go", value: String(f.r2_r7_no_go) },
  ];
}

// discrete frontier → operator 경고 배너(recall probe=routing only≠merge·lift≠same-event·near-match 0≠증명·gold 0·No-Go).
// backend required_copy(§9) 를 우선 표시하고, 누락 시 로컬 상수로 보강(defense-in-depth).
export function r1DiscreteFrontierWarnings(
  f: InternalOpsDiscreteAcquisitionFrontier,
): string[] {
  const out: string[] = [...(f.required_copy ?? [])];
  const ensure = (s: string) => {
    if (!out.includes(s)) out.push(s);
  };
  ensure(OPS_DISCRETE_COPY.recallProbeRoutingOnly);
  ensure(OPS_DISCRETE_COPY.liftNotSameEvent);
  ensure(OPS_DISCRETE_COPY.newlyRoutedNotSameEvent);
  ensure(OPS_DISCRETE_COPY.zeroNotProof);
  ensure(OPS_DISCRETE_COPY.worklistNotTruth);
  if (f.production_gold_count === 0) {
    ensure(OPS_DISCRETE_COPY.goldZeroUntilLabels);
    ensure(OPS_DISCRETE_COPY.productionGoldZero);
  }
  if (f.r2_r7_no_go) ensure(OPS_DISCRETE_COPY.laddersNoGo);
  return out;
}

// ── ADR#81 provider breadth + named single-event seed + KO source path frontier view helpers ────────────
// 필수 copy(§10) — provider breadth=acquisition support≠truth·named seed=candidate generation≠same-event proof·
// community=event anchor 아님을 operator 가 명확히 보게. source role guard 유지·gold 0·R2~R7 No-Go 강제.
export const OPS_BREADTH_COPY = {
  breadthSupportNotTruth: "Provider breadth is acquisition support, not truth",
  namedSeedNotProof: "Named seed is candidate generation, not same-event proof",
  communityNotAnchor: "Community reaction is not an event anchor",
  productionGoldZero: "Production gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
} as const;

// provider breadth frontier → read-only 표시 행(9-카테고리 카운트·named seed·KO·live recall aggregate; per-pair score/same_event 0).
export function toR1BreadthFrontierDisplayRows(
  f: InternalOpsProviderBreadthFrontier,
): OpsDisplayRow[] {
  return [
    { label: "Provider breadth status", value: f.provider_breadth_status },
    { label: "Query-capable publishable providers", value: `${f.query_capable_provider_count}` },
    { label: "Feed-only publishable providers", value: `${f.feed_only_provider_count}` },
    { label: "Official sources", value: `${f.official_source_count}` },
    { label: "Search URL candidates (not truth until fetched)", value: `${f.search_url_candidate_count}` },
    { label: "KO official/news (anchor-eligible)", value: `${f.ko_official_news_count}` },
    { label: "Community (reaction-only, not anchor)", value: `${f.community_reaction_only_count}` },
    { label: "Market (signal-only, not anchor)", value: `${f.market_signal_only_count}` },
    { label: "Catalog (enrichment-only, not anchor)", value: `${f.catalog_enrichment_only_count}` },
    { label: "Unknown / quarantine (fail-closed)", value: `${f.unknown_quarantine_count}` },
    { label: "Anchor-eligible sources", value: `${f.anchor_eligible_count}` },
    { label: "Named seed bank status", value: f.named_seed_bank_status },
    { label: "Named single-event seeds", value: `${f.named_seed_count}` },
    { label: "Selected seed for next live run", value: f.selected_seed_for_next_live_run ?? "(none)" },
    { label: "Seed type", value: f.seed_type },
    { label: "KO source path status", value: f.ko_source_path_status },
    { label: "KO tokenization risk recorded", value: String(f.ko_tokenization_risk_recorded) },
    { label: "Live recall lift status", value: f.live_recall_lift_status },
    { label: "Live recall probe max score (routing signal, not truth)", value: `${f.max_live_recall_probe_score}` },
    { label: "Live pairs newly routed (not same-event)", value: `${f.newly_routed_count}` },
    { label: "Production candidate status", value: f.production_candidate_status },
    { label: "Blocked reason", value: f.blocked_reason || "(none)" },
    { label: "R1 gap", value: `${f.current_r1_gap}` },
    { label: "Acquisition next action", value: f.acquisition_next_action },
    { label: "R2~R7 No-Go", value: String(f.r2_r7_no_go) },
  ];
}

// provider breadth frontier → operator 경고 배너(breadth=support≠truth·named seed≠proof·community≠anchor·gold 0·No-Go).
// backend required_copy(§10) 를 우선 표시하고, 누락 시 로컬 상수로 보강(defense-in-depth).
export function r1BreadthFrontierWarnings(
  f: InternalOpsProviderBreadthFrontier,
): string[] {
  const out: string[] = [...(f.required_copy ?? [])];
  const ensure = (s: string) => {
    if (!out.includes(s)) out.push(s);
  };
  ensure(OPS_BREADTH_COPY.breadthSupportNotTruth);
  ensure(OPS_BREADTH_COPY.namedSeedNotProof);
  ensure(OPS_BREADTH_COPY.communityNotAnchor);
  ensure(OPS_BREADTH_COPY.productionGoldZero);
  if (f.r2_r7_no_go) ensure(OPS_BREADTH_COPY.laddersNoGo);
  return out;
}

// 필수 copy(§10·ADR#82) — bounded live run 은 operator 확인 date-pinned event 요구·provider breadth=support≠truth·
// production candidate freeze=reviewer worklist≠same-event truth 를 operator 가 명확히 보게. gold 0·R2~R7 No-Go 강제.
export const OPS_BOUNDED_COPY = {
  breadthSupportNotTruth: "Provider breadth is acquisition support, not truth",
  namedSeedNotProof: "Named seed is candidate generation, not same-event proof",
  liveRunNeedsDatePin: "A bounded live run requires an operator-confirmed date-pinned event",
  communityNotAnchor: "Community reaction is not an event anchor",
  freezeNotTruth: "Production candidate freeze is a reviewer worklist, not same-event truth",
  productionGoldZero: "Production gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
} as const;

// bounded live breadth frontier → read-only 표시 행(date-pin status·실행가능 pool 카운트·freeze status·KO lane;
// per-pair score/same_event/raw body 0). provider_breadth_used 는 *adapter_wired ∩ credential 교집합*(breadth 크기 아님).
export function toR1BoundedLiveBreadthFrontierDisplayRows(
  f: InternalOpsBoundedLiveBreadthFrontier,
): OpsDisplayRow[] {
  return [
    { label: "Bounded live run status", value: f.latest_bounded_live_run_status },
    { label: "Named seed selected", value: f.named_seed_selected ?? "(none)" },
    { label: "Named seed date-pin status", value: f.named_seed_date_pin_status },
    { label: "Selected seed actual occurrence", value: f.selected_seed_actual_occurrence ?? "(not pinned)" },
    { label: "Live query approved", value: String(f.live_query_approved) },
    { label: "Live query executed", value: String(f.live_query_executed) },
    { label: "Live call count", value: `${f.live_call_count}` },
    { label: "Providers used (actual)", value: f.providers_used.length ? f.providers_used.join(", ") : "(none)" },
    { label: "Provider breadth used (adapter-wired ∩ credential)", value: `${f.provider_breadth_used}` },
    { label: "Key-free providers in pool", value: `${f.key_free_provider_count}` },
    { label: "Credential-required providers in pool", value: `${f.credential_required_provider_count}` },
    { label: "Comparison pair count", value: `${f.comparison_pair_count}` },
    { label: "Live recall probe max score (routing signal, not truth)", value: `${f.max_recall_probe_score}` },
    { label: "Live pairs newly routed (not same-event)", value: `${f.newly_routed_count}` },
    { label: "Production candidate status", value: f.production_candidate_status },
    { label: "Production candidate batch ready", value: String(f.production_candidate_batch_ready) },
    { label: "Production frozen pair count (worklist, not truth)", value: `${f.production_frozen_pair_count}` },
    { label: "Sanitized snapshot status", value: f.sanitized_snapshot_status },
    { label: "KO source lane status", value: f.ko_source_lane_status },
    { label: "KO named seed needed", value: String(f.ko_named_seed_needed) },
    { label: "KO floor", value: `${f.ko_floor_current}/${f.ko_floor_required}` },
    { label: "Blocked reason", value: f.blocked_reason || "(none)" },
    { label: "Acquisition next action", value: f.acquisition_next_action },
    { label: "R1 gap", value: `${f.current_r1_gap}` },
    { label: "Production gold count", value: `${f.production_gold_count}` },
    { label: "R2~R7 No-Go", value: String(f.r2_r7_no_go) },
  ];
}

// bounded live breadth frontier → operator 경고 배너(breadth=support≠truth·named seed≠proof·live run 은 date-pin 요구·
// community≠anchor·freeze≠truth·gold 0·No-Go). backend required_copy(§10) 우선, 누락 시 로컬 상수 보강(defense-in-depth).
export function r1BoundedLiveBreadthFrontierWarnings(
  f: InternalOpsBoundedLiveBreadthFrontier,
): string[] {
  const out: string[] = [...(f.required_copy ?? [])];
  const ensure = (s: string) => {
    if (!out.includes(s)) out.push(s);
  };
  ensure(OPS_BOUNDED_COPY.breadthSupportNotTruth);
  ensure(OPS_BOUNDED_COPY.namedSeedNotProof);
  ensure(OPS_BOUNDED_COPY.liveRunNeedsDatePin);
  ensure(OPS_BOUNDED_COPY.communityNotAnchor);
  ensure(OPS_BOUNDED_COPY.freezeNotTruth);
  ensure(OPS_BOUNDED_COPY.productionGoldZero);
  if (f.r2_r7_no_go) ensure(OPS_BOUNDED_COPY.laddersNoGo);
  return out;
}

// ADR#83 — date-pinned live run frontier 정직 copy(date-pin=operator 게이트≠발생 증명·live query=operator event≠
// curated fallback·freeze=worklist≠truth·gold 0·No-Go). backend required_copy(§13) 우선·로컬은 defense-in-depth.
export const OPS_DATE_PINNED_COPY = {
  operatorEventRequired: "A date-pinned operator event is required before any bounded live run",
  occurrenceIsAssertion: "occurrence_date is an operator assertion, not a code-verified fact",
  datePinNotOccurrence: "A date pin does not prove the event occurred or that both sources cover it",
  queryTargetsOperatorEvent: "The live query targets the operator event, never a curated seed fallback",
  freezeNotTruth: "Production candidate freeze is a reviewer worklist, not same-event truth",
  productionGoldZero: "Production gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
} as const;

// date-pinned live run frontier → read-only 표시 행(operator event provided·occurrence_date(operator 주장)·target
// wired·live executed·freeze status·KO lane; per-pair score/same_event/raw body/named_entity 전문 0). operator 가
// 다음에 할 일(date-pinned event 제공 → bounded live 승인)을 한 눈에 보여준다.
export function toR1DatePinnedLiveRunFrontierDisplayRows(
  f: InternalOpsDatePinnedLiveRunFrontier,
): OpsDisplayRow[] {
  return [
    { label: "Date-pinned live run status", value: f.latest_date_pinned_live_run_status },
    { label: "Operator event provided", value: String(f.operator_event_provided) },
    { label: "Occurrence date (operator assertion, unverified)", value: f.occurrence_date ?? "(not provided)" },
    { label: "Occurrence date valid ISO", value: String(f.occurrence_date_valid_iso) },
    { label: "Date-pinned named event valid", value: String(f.date_pinned_named_event_valid) },
    { label: "Live query target wired", value: String(f.live_query_target_wired) },
    { label: "Live query approved", value: String(f.live_query_approved) },
    { label: "Live query executed", value: String(f.live_query_executed) },
    { label: "Live call count", value: `${f.live_call_count}` },
    { label: "Providers used (actual)", value: f.providers_used.length ? f.providers_used.join(", ") : "(none)" },
    { label: "Comparison pair count", value: `${f.comparison_pair_count}` },
    { label: "Live recall probe max score (routing signal, not truth)", value: `${f.max_recall_probe_score}` },
    { label: "Live pairs newly routed (not same-event)", value: `${f.newly_routed_count}` },
    { label: "Production candidate status", value: f.production_candidate_status },
    { label: "Production candidate batch ready", value: String(f.production_candidate_batch_ready) },
    { label: "Production frozen pair count (worklist, not truth)", value: `${f.production_frozen_pair_count}` },
    { label: "Candidate provenance", value: f.candidate_provenance },
    { label: "Sanitized snapshot status", value: f.sanitized_snapshot_status },
    { label: "Date window enforced (out-of-window dropped)", value: String(f.date_window_enforced) },
    { label: "Reviewer handoff ready (pre-contact; no sending)", value: String(f.reviewer_handoff_ready) },
    { label: "KO source lane status", value: f.ko_source_lane_status },
    { label: "KO named seed needed", value: String(f.ko_named_seed_needed) },
    { label: "KO floor", value: `${f.ko_floor_current}/${f.ko_floor_required}` },
    { label: "Blocked reason", value: f.blocked_reason || "(none)" },
    { label: "Acquisition next action", value: f.acquisition_next_action },
    { label: "R1 gap", value: `${f.current_r1_gap}` },
    { label: "Production gold count", value: `${f.production_gold_count}` },
    { label: "R2~R7 No-Go", value: String(f.r2_r7_no_go) },
  ];
}

// date-pinned live run frontier → operator 경고 배너(operator event 필요·occurrence=주장·date-pin≠발생·query=operator
// event≠curated·freeze≠truth·gold 0·No-Go). backend required_copy(§13) 우선, 누락 시 로컬 상수 보강(defense-in-depth).
export function r1DatePinnedLiveRunFrontierWarnings(
  f: InternalOpsDatePinnedLiveRunFrontier,
): string[] {
  const out: string[] = [...(f.required_copy ?? [])];
  const ensure = (s: string) => {
    if (!out.includes(s)) out.push(s);
  };
  ensure(OPS_DATE_PINNED_COPY.operatorEventRequired);
  ensure(OPS_DATE_PINNED_COPY.occurrenceIsAssertion);
  ensure(OPS_DATE_PINNED_COPY.datePinNotOccurrence);
  ensure(OPS_DATE_PINNED_COPY.queryTargetsOperatorEvent);
  ensure(OPS_DATE_PINNED_COPY.freezeNotTruth);
  ensure(OPS_DATE_PINNED_COPY.productionGoldZero);
  if (f.r2_r7_no_go) ensure(OPS_DATE_PINNED_COPY.laddersNoGo);
  return out;
}
