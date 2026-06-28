import { describe, it } from "node:test";
import assert from "node:assert/strict";

// 코드베이스 convention(client.test.mjs): node:test 는 TS 로더가 없으므로 순수 로직을 inline 재선언해 계약을
// 잠근다. 본 helper 의 1차 보증은 서버측(Python _assert_pii_safe + Pydantic 화이트리스트 + API forbidden-field
// 테스트). 이 테스트는 표시층이 forbidden 필드를 re-introduce 하지 않는다는 2차 lock 이다.
const FORBIDDEN_OPS_FIELDS = [
  "score", "model_score", "rationale", "predicted_status", "same_event", "raw_body", "body",
  "reviewer_name", "name", "reviewer_email", "reviewer_phone", "email", "phone", "secret", "api_key",
  "provider_secret", "hidden_rank", "source_hidden_rank",
];

const OPS_NO_GO_COPY = {
  heading: "Internal operations status",
  notPublicTruth: "Not public truth",
  noMerge: "No merge allowed",
  goldUnverified: "Gold not verified yet",
  awaitingReturn: "Awaiting reviewer return",
  requiresMergeGate: "Requires MERGE_GATE before public IU",
};

function assertOpsContractSafe(contract) {
  const walk = (o) => {
    if (Array.isArray(o)) {
      o.forEach(walk);
      return;
    }
    if (o && typeof o === "object") {
      for (const [k, v] of Object.entries(o)) {
        if (FORBIDDEN_OPS_FIELDS.includes(k)) {
          throw new Error(`internal ops contract leaked forbidden field: ${k}`);
        }
        walk(v);
      }
    }
  };
  walk(contract);
}

function toOpsDisplayRows(c) {
  return [
    { label: "Execution status", value: c.execution_status },
    { label: "Pilot status", value: c.pilot_status },
    { label: "Contacted reviewers", value: `${c.real_reviewers_contacted}` },
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

const SAMPLE = {
  contract: "InternalOpsPilotExecutionStatus",
  batch_id: "b1",
  pilot_status: "not_ready",
  execution_status: "not_started",
  contact_evidence_present: false,
  real_reviewers_contacted: 0,
  returned_label_count: 0,
  missing_label_count: 0,
  invalid_label_count: 0,
  invalid_file_count: 0,
  conflict_pair_count: 0,
  overdue_count: 0,
  production_gold_count: 0,
  synthetic_gold_count: 0,
  production_gold_provenance_verified: false,
  calibration_ready: false,
  merge_gate_ready: false,
  next_action: "awaiting external input",
  flags: {
    internal_only: true, no_public_truth: true, no_merge: true, no_public_iu: true,
    pii_safe: true, no_llm: true, no_db_write: true, gold_provenance_verified: false,
  },
};

describe("assertOpsContractSafe", () => {
  it("passes a clean sanitized contract", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE));
  });

  it("throws on a top-level forbidden field", () => {
    assert.throws(() => assertOpsContractSafe({ ...SAMPLE, score: 0.9 }), /forbidden field: score/);
  });

  it("throws on a nested forbidden field", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE, extra: [{ rationale: "leak" }] }),
      /forbidden field: rationale/,
    );
  });

  it("throws on predicted_status / raw PII", () => {
    assert.throws(() => assertOpsContractSafe({ ...SAMPLE, predicted_status: "x" }));
    assert.throws(() => assertOpsContractSafe({ ...SAMPLE, reviewer_email: "a@b.c" }));
  });
});

describe("toOpsDisplayRows", () => {
  it("maps workflow state to rows including execution_status", () => {
    const rows = toOpsDisplayRows(SAMPLE);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Execution status"], "not_started");
    assert.equal(byLabel["Production gold (unverified)"], "0");
    assert.equal(byLabel["Merge gate ready"], "false");
  });

  it("emits only string values (no leaked objects)", () => {
    for (const row of toOpsDisplayRows(SAMPLE)) {
      assert.equal(typeof row.value, "string");
    }
  });
});

describe("OPS_NO_GO_COPY", () => {
  it("carries the required no-go statements", () => {
    assert.equal(OPS_NO_GO_COPY.heading, "Internal operations status");
    assert.ok(OPS_NO_GO_COPY.notPublicTruth.includes("Not public truth"));
    assert.ok(OPS_NO_GO_COPY.noMerge.includes("No merge"));
    assert.ok(OPS_NO_GO_COPY.requiresMergeGate.includes("MERGE_GATE"));
  });
});

// ── ADR#73 preflight view(auth/deploy posture + R1~R7 readiness) — inline 재선언 lock ──
const OPS_PREFLIGHT_COPY = {
  externalInputRequired: "Awaiting actual returned labels — external reviewer input required",
  unsafeExposure: "UNSAFE: dashboard enabled without auth in a non-production environment",
  misconfigured: "Misconfigured: dashboard enabled without admin token in a prod-like environment",
  deploymentUnproven: "Deployment boundary not proven (per-user auth absent — internal only)",
};

function toPreflightDisplayRows(p) {
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

function preflightWarnings(p) {
  const out = [];
  if (p.preflight_status === "unsafe_public_exposure") out.push(OPS_PREFLIGHT_COPY.unsafeExposure);
  if (p.preflight_status === "misconfigured") out.push(OPS_PREFLIGHT_COPY.misconfigured);
  if (p.external_input_required) out.push(OPS_PREFLIGHT_COPY.externalInputRequired);
  if (!p.deployment_proven) out.push(OPS_PREFLIGHT_COPY.deploymentUnproven);
  return out;
}

const SAMPLE_PREFLIGHT = {
  contract: "InternalOpsPreflightStatus",
  preflight_status: "disabled_safe",
  auth_boundary_status: "hardened_partial",
  app_env: "dev",
  admin_token_required: true,
  admin_token_configured: false,
  feature_flag_required: true,
  feature_flag_enabled: false,
  frontend_server_env_required: true,
  public_nav_exposed: false,
  deployment_proven: false,
  actual_input_status: "no_actual_input",
  external_input_required: true,
  production_gold_count: 0,
  calibration_ready: false,
  merge_gate_ready: false,
  r1_r7_readiness_matrix_ready: true,
  r1_r7_stages: [
    { stage: "R1", goal: "production gold floor", current_status: "FAIL",
      blocker: "actual returned labels", next_action: "collect labels" },
    { stage: "R7", goal: "Agent synthesis / Intelligence Unit", current_status: "No-Go",
      blocker: "R1-R6 gates unmet", next_action: "gated synthesis only after all gates" },
  ],
  flags: {
    internal_only: true, no_public_truth: true, no_merge: true, no_public_iu: true,
    pii_safe: true, no_llm: true, no_db_write: true, gold_provenance_verified: false,
  },
  block_reasons: ["dashboard_disabled"],
  next_actions: ["keep INTERNAL_OPS_DASHBOARD_ENABLED off unless internal operator access is needed"],
};

describe("preflight view", () => {
  it("passes the forbidden-field guard (no score/rationale/predicted_status/PII/token)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_PREFLIGHT));
  });

  it("never exposes an admin token value (only the configured bool)", () => {
    const blob = JSON.stringify(SAMPLE_PREFLIGHT);
    assert.ok(!/token['"]?\s*[:=]\s*['"][A-Za-z0-9]/.test(blob)); // no token value pattern.
    assert.equal(SAMPLE_PREFLIGHT.admin_token_configured, false);
  });

  it("maps posture to string rows only", () => {
    const rows = toPreflightDisplayRows(SAMPLE_PREFLIGHT);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Preflight status"], "disabled_safe");
    assert.equal(byLabel["Deployment proven"], "false");
    assert.equal(byLabel["External input required"], "true");
    for (const row of rows) assert.equal(typeof row.value, "string");
  });

  it("derives external-input + deployment-unproven warnings", () => {
    const w = preflightWarnings(SAMPLE_PREFLIGHT);
    assert.ok(w.includes(OPS_PREFLIGHT_COPY.externalInputRequired));
    assert.ok(w.includes(OPS_PREFLIGHT_COPY.deploymentUnproven));
  });

  it("flags unsafe_public_exposure prominently", () => {
    const w = preflightWarnings({ ...SAMPLE_PREFLIGHT, preflight_status: "unsafe_public_exposure" });
    assert.ok(w.includes(OPS_PREFLIGHT_COPY.unsafeExposure));
  });

  it("throws if a forbidden field is re-introduced into the preflight contract", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_PREFLIGHT, r1_r7_stages: [{ stage: "R1", score: 0.9 }] }),
      /forbidden field: score/,
    );
  });

  it("carries R1–R7 readiness stages (gated, no anchor)", () => {
    assert.equal(SAMPLE_PREFLIGHT.r1_r7_readiness_matrix_ready, true);
    assert.equal(SAMPLE_PREFLIGHT.r1_r7_stages[0].stage, "R1");
    assert.equal(SAMPLE_PREFLIGHT.r1_r7_stages[0].current_status, "FAIL");
  });
});

// ── ADR#74 R1 gold acquisition view(gap + operator next action) — inline 재선언 lock ──
const OPS_R1_COPY = {
  blockedByLabels: "R1 is blocked by actual returned labels",
  goldZeroUntilImport: "Gold count is 0 until human production labels are imported",
  laddersNoGo: "R2~R7 remain No-Go",
  internalOnly: "Internal operations only",
  notPublicTruth: "Not public truth",
};

function toR1DisplayRows(r) {
  const cr = (cur, req, gap) => `${cur} / ${req} (gap ${gap})`;
  return [
    { label: "R1 status", value: r.r1_status },
    { label: "Actual input status", value: r.actual_input_status },
    { label: "Production gold (unverified)", value: cr(r.current_production_gold_count, r.required_production_gold_count, r.label_collection_gap) },
    { label: "Korean gold", value: cr(r.current_korean_gold_count, r.required_korean_gold_count, r.korean_gap) },
    { label: "Positive gold", value: cr(r.current_positive_gold_count, r.required_positive_gold_count, r.positive_gap) },
    { label: "Negative gold", value: cr(r.current_negative_gold_count, r.required_negative_gold_count, r.negative_gap) },
    { label: "Hard-negative gold", value: cr(r.current_hard_negative_count, r.required_hard_negative_count, r.hard_negative_gap) },
    { label: "Reviewers engaged (>=2 required)", value: cr(r.current_reviewer_count, r.reviewer_count_required, r.reviewer_gap) },
    { label: "Reviewer agreement required", value: String(r.reviewer_agreement_required) },
    { label: "Conflict adjudication required", value: String(r.conflict_adjudication_required) },
    { label: "Calibration ready", value: String(r.calibration_ready) },
    { label: "Merge gate ready", value: String(r.merge_gate_ready) },
  ];
}

function r1Warnings(r) {
  const out = [];
  if (r.r1_status === "blocked_no_labels") out.push(OPS_R1_COPY.blockedByLabels);
  if (r.current_production_gold_count === 0) out.push(OPS_R1_COPY.goldZeroUntilImport);
  if (!r.merge_gate_ready) out.push(OPS_R1_COPY.laddersNoGo);
  return out;
}

const SAMPLE_R1 = {
  contract: "InternalOpsR1AcquisitionStatus",
  r1_status: "blocked_no_labels",
  actual_input_status: "no_actual_input",
  external_input_required: true,
  current_production_gold_count: 0,
  required_production_gold_count: 200,
  current_korean_gold_count: 0,
  required_korean_gold_count: 50,
  current_positive_gold_count: 0,
  current_negative_gold_count: 0,
  required_positive_gold_count: 67,
  required_negative_gold_count: 67,
  current_hard_negative_count: 0,
  required_hard_negative_count: 20,
  current_reviewer_count: 0,
  reviewer_count_required: 2,
  reviewer_duplication_required: 2,
  reviewer_agreement_required: true,
  conflict_adjudication_required: true,
  label_collection_gap: 200,
  korean_gap: 50,
  positive_gap: 67,
  negative_gap: 67,
  hard_negative_gap: 20,
  reviewer_gap: 2,
  calibration_ready: false,
  merge_gate_ready: false,
  next_manual_actions: [
    "recruit >=2 reviewers per pair (pseudonymous ids; raw roster/mapping local-only, never committed)",
    "two-reviewer agreement required; resolve conflicts by human-only adjudication (no auto-majority gold)",
  ],
  flags: {
    internal_only: true, no_public_truth: true, no_merge: true, no_public_iu: true,
    pii_safe: true, no_llm: true, no_db_write: true, gold_provenance_verified: false,
  },
};

describe("r1 acquisition view", () => {
  it("passes the forbidden-field guard (no score/rationale/predicted_status/PII)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_R1));
  });

  it("maps gold floor to current/required/gap string rows", () => {
    const rows = toR1DisplayRows(SAMPLE_R1);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["R1 status"], "blocked_no_labels");
    assert.equal(byLabel["Production gold (unverified)"], "0 / 200 (gap 200)");
    assert.equal(byLabel["Korean gold"], "0 / 50 (gap 50)");
    assert.equal(byLabel["Positive gold"], "0 / 67 (gap 67)");
    assert.equal(byLabel["Hard-negative gold"], "0 / 20 (gap 20)");
    for (const row of rows) assert.equal(typeof row.value, "string");
  });

  it("derives blocked + gold-zero + R2~R7 No-Go warnings", () => {
    const w = r1Warnings(SAMPLE_R1);
    assert.ok(w.includes(OPS_R1_COPY.blockedByLabels));
    assert.ok(w.includes(OPS_R1_COPY.goldZeroUntilImport));
    assert.ok(w.includes(OPS_R1_COPY.laddersNoGo));
  });

  it("carries required no-go copy statements", () => {
    assert.ok(OPS_R1_COPY.blockedByLabels.includes("blocked by actual returned labels"));
    assert.ok(OPS_R1_COPY.goldZeroUntilImport.includes("Gold count is 0"));
    assert.ok(OPS_R1_COPY.laddersNoGo.includes("No-Go"));
    assert.ok(OPS_R1_COPY.internalOnly.includes("Internal operations only"));
  });

  it("throws if a forbidden field is re-introduced into the R1 contract", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_R1, predicted_status: "same_event" }),
      /forbidden field: predicted_status/,
    );
  });

  it("never carries a same_event truth field", () => {
    assert.throws(() => assertOpsContractSafe({ ...SAMPLE_R1, same_event: true }), /forbidden field: same_event/);
  });
});

// ── ADR#75 R1 pilot batch view(freeze + launch readiness) — inline 재선언 lock ──
const OPS_R1_BATCH_COPY = {
  worklistNotTruth: "Frozen batch is a reviewer worklist, not truth",
  manualLaunchRequired: "Manual launch required",
  returnedLabelsMissing: "Returned labels are still missing",
  goldZeroUntilImport: "Production gold remains 0 until human labels are imported",
  laddersNoGo: "R2~R7 remain No-Go",
  syntheticFixture: "Synthetic fixture pilot — production candidates require live source overlap",
};

function toR1BatchDisplayRows(b) {
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

function r1BatchWarnings(b) {
  const out = [OPS_R1_BATCH_COPY.worklistNotTruth];
  if (b.ready_for_manual_launch) out.push(OPS_R1_BATCH_COPY.manualLaunchRequired);
  if (!b.returned_labels_found) out.push(OPS_R1_BATCH_COPY.returnedLabelsMissing);
  if (b.production_gold_count === 0) out.push(OPS_R1_BATCH_COPY.goldZeroUntilImport);
  if (b.r2_r7_no_go) out.push(OPS_R1_BATCH_COPY.laddersNoGo);
  if (!b.pilot_batch_is_production_candidate) out.push(OPS_R1_BATCH_COPY.syntheticFixture);
  return out;
}

const SAMPLE_R1_BATCH = {
  contract: "InternalOpsR1PilotBatchStatus",
  pilot_batch_id: "reviewer_pilot_exec_001",
  batch_frozen: true,
  batch_signature: "sha256:6c0f451d9d06f03e",
  candidate_provenance: "synthetic_fixture",
  pilot_batch_is_production_candidate: false,
  frozen_pair_count: 5,
  target_pair_count: 200,
  expected_label_file_count: 2,
  launch_status: "ready_for_manual_launch",
  ready_for_manual_launch: true,
  returned_labels_found: false,
  returned_label_count: 0,
  intake_directory: "outputs/reviewer_batch/reviewer_pilot_exec_001/intake",
  validation_command: ".\\.venv\\Scripts\\python.exe -m backend.app.tools.reviewer_batch_launch --validate outputs/reviewer_batch/reviewer_pilot_exec_001/intake --batch-id reviewer_pilot_exec_001",
  r1_status: "blocked_no_labels",
  production_gold_count: 0,
  required_production_gold_count: 200,
  current_r1_gap: 200,
  r2_r7_no_go: true,
  next_manual_action: "operator: manually distribute the frozen worklist + instruction + label template",
  flags: {
    internal_only: true, no_public_truth: true, no_merge: true, no_public_iu: true,
    pii_safe: true, no_llm: true, no_db_write: true, gold_provenance_verified: false,
  },
};

describe("r1 pilot batch view", () => {
  it("passes the forbidden-field guard (no score/rationale/predicted_status/PII)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_R1_BATCH));
  });

  it("maps launch readiness to string rows (frozen/provenance/pilot_n/gap)", () => {
    const rows = toR1BatchDisplayRows(SAMPLE_R1_BATCH);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Launch status"], "ready_for_manual_launch");
    assert.equal(byLabel["Candidate provenance"], "synthetic_fixture");
    assert.equal(byLabel["Production candidate"], "false");
    assert.equal(byLabel["Frozen pairs (pilot_n)"], "5 / 200");
    assert.equal(byLabel["Production gold (unverified)"], "0 / 200 (gap 200)");
    assert.equal(byLabel["R2~R7 No-Go"], "true");
    for (const row of rows) assert.equal(typeof row.value, "string");
  });

  it("derives worklist-not-truth + manual-launch + missing-labels + synthetic warnings", () => {
    const w = r1BatchWarnings(SAMPLE_R1_BATCH);
    assert.ok(w.includes(OPS_R1_BATCH_COPY.worklistNotTruth));
    assert.ok(w.includes(OPS_R1_BATCH_COPY.manualLaunchRequired));
    assert.ok(w.includes(OPS_R1_BATCH_COPY.returnedLabelsMissing));
    assert.ok(w.includes(OPS_R1_BATCH_COPY.goldZeroUntilImport));
    assert.ok(w.includes(OPS_R1_BATCH_COPY.laddersNoGo));
    assert.ok(w.includes(OPS_R1_BATCH_COPY.syntheticFixture));
  });

  it("carries required no-go copy statements", () => {
    assert.ok(OPS_R1_BATCH_COPY.worklistNotTruth.includes("worklist, not truth"));
    assert.ok(OPS_R1_BATCH_COPY.manualLaunchRequired.includes("Manual launch"));
    assert.ok(OPS_R1_BATCH_COPY.returnedLabelsMissing.includes("Returned labels are still missing"));
    assert.ok(OPS_R1_BATCH_COPY.goldZeroUntilImport.includes("Production gold remains 0"));
    assert.ok(OPS_R1_BATCH_COPY.laddersNoGo.includes("No-Go"));
  });

  it("marks the synthetic fixture as NOT a production candidate (no 둔갑)", () => {
    assert.equal(SAMPLE_R1_BATCH.candidate_provenance, "synthetic_fixture");
    assert.equal(SAMPLE_R1_BATCH.pilot_batch_is_production_candidate, false);
    assert.equal(SAMPLE_R1_BATCH.production_gold_count, 0);
  });

  it("throws if a forbidden field is re-introduced into the pilot batch contract", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_R1_BATCH, same_event: true }),
      /forbidden field: same_event/,
    );
  });
});

// ── ADR#76 R1 production candidate acquisition view(live · dual-track) — inline 재선언 lock ──
const OPS_R1_PROD_COPY = {
  syntheticNotProduction: "Synthetic dry-run batch is not production",
  requiresLivePairs: "Production candidate batch requires live-derived publishable pairs",
  worklistNotTruth: "Candidate worklist is not truth",
  returnedLabelsRequired: "Returned human labels are still required",
  goldZeroUntilImport: "Production gold remains 0 until human labels are imported",
  laddersNoGo: "R2~R7 remain No-Go",
};

function toR1ProdCandidateDisplayRows(p) {
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

function r1ProdCandidateWarnings(p) {
  const out = [OPS_R1_PROD_COPY.syntheticNotProduction, OPS_R1_PROD_COPY.worklistNotTruth];
  if (!p.production_candidate_batch_ready) out.push(OPS_R1_PROD_COPY.requiresLivePairs);
  if (p.production_gold_count === 0) out.push(OPS_R1_PROD_COPY.returnedLabelsRequired);
  if (p.production_gold_count === 0) out.push(OPS_R1_PROD_COPY.goldZeroUntilImport);
  if (p.r2_r7_no_go) out.push(OPS_R1_PROD_COPY.laddersNoGo);
  return out;
}

const SAMPLE_R1_PROD = {
  contract: "InternalOpsR1ProductionCandidateStatus",
  synthetic_dry_run_batch_ready: true,
  synthetic_batch_not_production: true,
  production_candidate_batch_ready: false,
  production_candidate_status: "blocked_no_live_opt_in",
  candidate_provenance: "none",
  live_call_performed: false,
  live_candidate_count: 0,
  publishable_pair_count: 0,
  production_frozen_pair_count: 0,
  production_batch_id: "",
  production_batch_signature: "",
  ready_for_manual_launch: false,
  blocked_no_live_production_candidates: true,
  validation_command: "",
  intake_directory: "",
  r1_status: "blocked_no_labels",
  production_gold_count: 0,
  required_production_gold_count: 200,
  current_r1_gap: 200,
  r2_r7_no_go: true,
  next_manual_action: "credentials are present — explicitly opt in to a bounded live query",
  flags: {
    internal_only: true, no_public_truth: true, no_merge: true, no_public_iu: true,
    pii_safe: true, no_llm: true, no_db_write: true, gold_provenance_verified: false,
  },
};

describe("r1 production candidate acquisition view (dual-track)", () => {
  it("passes the forbidden-field guard (no score/rationale/predicted_status/PII)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_R1_PROD));
  });

  it("separates synthetic dry-run from production-candidate batch (no 둔갑)", () => {
    const rows = toR1ProdCandidateDisplayRows(SAMPLE_R1_PROD);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Production candidate status"], "blocked_no_live_opt_in");
    assert.equal(byLabel["Synthetic dry-run batch ready"], "true");
    assert.equal(byLabel["Synthetic batch is non-production"], "true");
    assert.equal(byLabel["Production candidate batch ready"], "false");
    assert.equal(byLabel["Candidate provenance"], "none");
    assert.equal(byLabel["Blocked: no live production candidates"], "true");
    for (const row of rows) assert.equal(typeof row.value, "string");
  });

  it("derives synthetic-not-production + worklist-not-truth + live-pairs-required + No-Go warnings", () => {
    const w = r1ProdCandidateWarnings(SAMPLE_R1_PROD);
    assert.ok(w.includes(OPS_R1_PROD_COPY.syntheticNotProduction));
    assert.ok(w.includes(OPS_R1_PROD_COPY.worklistNotTruth));
    assert.ok(w.includes(OPS_R1_PROD_COPY.requiresLivePairs));
    assert.ok(w.includes(OPS_R1_PROD_COPY.returnedLabelsRequired));
    assert.ok(w.includes(OPS_R1_PROD_COPY.laddersNoGo));
  });

  it("carries required §7 no-go copy statements", () => {
    assert.ok(OPS_R1_PROD_COPY.syntheticNotProduction.includes("not production"));
    assert.ok(OPS_R1_PROD_COPY.requiresLivePairs.includes("live-derived publishable pairs"));
    assert.ok(OPS_R1_PROD_COPY.worklistNotTruth.includes("not truth"));
    assert.ok(OPS_R1_PROD_COPY.returnedLabelsRequired.includes("Returned human labels"));
    assert.ok(OPS_R1_PROD_COPY.laddersNoGo.includes("No-Go"));
  });

  it("does not mark a production candidate batch without live-derived pairs", () => {
    assert.equal(SAMPLE_R1_PROD.production_candidate_batch_ready, false);
    assert.equal(SAMPLE_R1_PROD.candidate_provenance, "none");
    assert.equal(SAMPLE_R1_PROD.production_gold_count, 0);
  });

  it("throws if a forbidden field is re-introduced into the production candidate contract", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_R1_PROD, predicted_status: "same_event" }),
      /forbidden field: predicted_status/,
    );
  });
});

// ── ADR#78 near-match gap diagnostic + targeted acquisition frontier — inline 재선언 lock ──
const OPS_FRONTIER_COPY = {
  zeroNotProof: "Near-match 0 does not prove no same event",
  causeUnresolved: "Cause unresolved: detector miss vs different-events vs provider narrowness",
  requiresLivePair: "Production candidate requires live-derived publishable pair",
  worklistNotTruth: "Production candidate is reviewer worklist, not truth",
  goldZeroUntilLabels: "R1 gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
};

function toR1FrontierDisplayRows(f) {
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

function r1FrontierWarnings(f) {
  const out = [...(f.required_copy ?? [])];
  const ensure = (s) => {
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

const SAMPLE_FRONTIER = {
  contract: "InternalOpsAcquisitionFrontier",
  near_match_gap_status: "all_below_hard_floor",
  root_cause_hypotheses: [
    { cause: "same_event_possible_but_detector_missed", signal: "plausible" },
    { cause: "broad_topic_different_events", signal: "plausible" },
    { cause: "title_normalization_gap", signal: "plausible" },
    { cause: "provider_pair_narrowness", signal: "plausible" },
    { cause: "time_window_mismatch", signal: "weak" },
    { cause: "source_role_metadata_gap", signal: "not_indicated" },
    { cause: "unknown", signal: "supporting" },
  ],
  root_cause_confidence: "indeterminate",
  targeted_query_seed_count: 3,
  live_attempt_count: 2,
  live_candidate_count: 30,
  publishable_pair_count: 0,
  production_candidate_status: "blocked_no_publishable_pairs",
  production_candidate_batch_ready: false,
  candidate_provenance: "none",
  provider_expansion_plan_ready: true,
  korean_source_strategy_ready: true,
  blocked_reason: "blocked_no_publishable_pairs",
  current_r1_gap: 200,
  production_gold_count: 0,
  r2_r7_no_go: true,
  required_copy: [
    "Near-match 0 does not prove no same event",
    "Cause unresolved: detector miss vs different-events vs provider narrowness",
    "Production candidate requires live-derived publishable pair",
    "Production candidate is reviewer worklist, not truth",
    "R1 gold remains 0 until human labels are returned",
    "R2~R7 remain No-Go",
  ],
  flags: {
    no_public_truth: true, no_same_event_truth: true, no_score: true, no_rationale: true,
    no_predicted_status: true, no_raw_body: true, no_secret: true,
  },
};

describe("ADR#78 acquisition frontier view", () => {
  it("passes the sanitized frontier contract (no forbidden fields)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_FRONTIER));
  });

  it("shows near-match gap status + indeterminate confidence (not asserted as truth)", () => {
    const rows = toR1FrontierDisplayRows(SAMPLE_FRONTIER);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Near-match gap status"], "all_below_hard_floor");
    assert.equal(byLabel["Root-cause confidence"], "indeterminate");
    // 가설은 표시되되 같은/다른 사건을 단정하지 않는다(둘 다 plausible 로 병기).
    assert.ok(byLabel["Root-cause hypotheses (not asserted)"].includes("same_event_possible_but_detector_missed"));
    assert.ok(byLabel["Root-cause hypotheses (not asserted)"].includes("broad_topic_different_events"));
  });

  it("labels live candidate pairs as comparison, not match", () => {
    const rows = toR1FrontierDisplayRows(SAMPLE_FRONTIER);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Live candidate pairs (comparison, not match)"], "30");
    assert.equal(byLabel["Publishable near-match pairs"], "0");
  });

  it("emits only string values (no leaked objects)", () => {
    for (const row of toR1FrontierDisplayRows(SAMPLE_FRONTIER)) {
      assert.equal(typeof row.value, "string");
    }
  });

  it("warns: near-match 0 is not proof + cause unresolved + worklist not truth + gold 0 + No-Go", () => {
    const w = r1FrontierWarnings(SAMPLE_FRONTIER);
    assert.ok(w.includes(OPS_FRONTIER_COPY.zeroNotProof));
    assert.ok(w.includes(OPS_FRONTIER_COPY.causeUnresolved));
    assert.ok(w.includes(OPS_FRONTIER_COPY.worklistNotTruth));
    assert.ok(w.includes(OPS_FRONTIER_COPY.requiresLivePair));
    assert.ok(w.includes(OPS_FRONTIER_COPY.goldZeroUntilLabels));
    assert.ok(w.includes(OPS_FRONTIER_COPY.laddersNoGo));
  });

  it("carries the required §11 honesty copy", () => {
    assert.ok(OPS_FRONTIER_COPY.zeroNotProof.includes("does not prove no same event"));
    assert.ok(OPS_FRONTIER_COPY.causeUnresolved.includes("Cause unresolved"));
    assert.ok(OPS_FRONTIER_COPY.worklistNotTruth.includes("not truth"));
    assert.ok(OPS_FRONTIER_COPY.laddersNoGo.includes("No-Go"));
  });

  it("throws if a forbidden field is re-introduced into the frontier contract", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_FRONTIER, score: 0.9 }),
      /forbidden field: score/,
    );
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_FRONTIER, extra: [{ same_event: true }] }),
      /forbidden field: same_event/,
    );
  });
});

// ── ADR#79 discrete-event acquisition + deterministic recall probe frontier — inline 재선언 lock ──
const OPS_DISCRETE_COPY = {
  recallProbeRoutingOnly: "Recall probe is reviewer-routing only, not merge",
  liftNotSameEvent: "Recall probe lift on synthetic does not assert same-event on live frontier",
  newlyRoutedNotSameEvent: "Newly routed does not mean same event",
  productionGoldZero: "Production gold remains 0 until human labels are returned",
  zeroNotProof: "Near-match 0 does not prove no same event",
  worklistNotTruth: "Production candidate is reviewer worklist, not truth",
  goldZeroUntilLabels: "R1 gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
};

function toR1DiscreteFrontierDisplayRows(f) {
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

function r1DiscreteFrontierWarnings(f) {
  const out = [...(f.required_copy ?? [])];
  const ensure = (s) => {
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

const SAMPLE_DISCRETE_FRONTIER = {
  contract: "InternalOpsDiscreteAcquisitionFrontier",
  discrete_event_seed_selected: "fomc_decision",
  discrete_event_seed_source: "code_proposed_shape",
  discrete_event_time_window: "1d",
  discrete_seed_valid_count: 3,
  near_match_gap_status: "insufficient_debug_artifact",
  root_cause_hypotheses: [
    { cause: "insufficient_debug_artifact", signal: "supporting" },
  ],
  root_cause_confidence: "n/a",
  max_recall_probe_score: 1.0,
  recall_probe_pairs_newly_routed: 2,
  recall_probe_applies_to_merge: false,
  recall_probe_lever_demonstrated: true,
  max_live_recall_probe_score: 0.0,
  live_pairs_newly_routed_by_probe: 0,
  live_recall_lift_status: "live_blocked_by_rate_or_opt_in",
  live_frontier_verdict: "live_blocked_by_rate_or_opt_in",
  live_candidate_count: 0,
  production_candidate_status: "blocked_no_live_opt_in",
  blocked_reason: "blocked_no_live_opt_in",
  provider_breadth_next_action: "wire GDELT cooldown-honored + key-free RSS multi-outlet fleet for breadth",
  korean_source_next_action: "wire naver_news_search adapter for KO topic-targeted overlap (KO floor lever)",
  current_r1_gap: 200,
  production_gold_count: 0,
  r2_r7_no_go: true,
  required_copy: [
    "Near-match 0 does not prove no same event",
    "Recall probe is reviewer-routing only, not merge",
    "Newly routed does not mean same event",
    "Production gold remains 0 until human labels are returned",
    "R2~R7 remain No-Go",
  ],
  flags: {
    no_public_truth: true, no_same_event_truth: true, no_score: true, no_rationale: true,
    no_predicted_status: true, no_raw_body: true, no_secret: true,
  },
};

describe("ADR#79 discrete acquisition + recall probe frontier view", () => {
  it("passes the sanitized frontier contract (no forbidden fields; max_recall_probe_score is not 'score')", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_DISCRETE_FRONTIER));
  });

  it("shows the discrete seed shape + source (acquisition intent, not a fabricated event)", () => {
    const rows = toR1DiscreteFrontierDisplayRows(SAMPLE_DISCRETE_FRONTIER);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Discrete event seed"], "fomc_decision");
    assert.equal(byLabel["Seed source"], "code_proposed_shape");
    assert.equal(byLabel["Time window"], "1d");
  });

  it("labels recall probe max score as routing signal, not truth; applies-to-merge is false", () => {
    const rows = toR1DiscreteFrontierDisplayRows(SAMPLE_DISCRETE_FRONTIER);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Recall probe max score (routing signal, not truth)"], "1");
    assert.equal(byLabel["Recall probe applies to merge"], "false");
    assert.equal(byLabel["Recall probe pairs newly routed"], "2");
  });

  it("labels live candidate pairs as comparison, not match", () => {
    const rows = toR1DiscreteFrontierDisplayRows(SAMPLE_DISCRETE_FRONTIER);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));
    assert.equal(byLabel["Live candidate pairs (comparison, not match)"], "0");
  });

  it("emits only string values (no leaked objects)", () => {
    for (const row of toR1DiscreteFrontierDisplayRows(SAMPLE_DISCRETE_FRONTIER)) {
      assert.equal(typeof row.value, "string");
    }
  });

  it("warns: recall probe is routing-only not merge + lift != same-event + gold 0 + No-Go", () => {
    const w = r1DiscreteFrontierWarnings(SAMPLE_DISCRETE_FRONTIER);
    assert.ok(w.includes(OPS_DISCRETE_COPY.recallProbeRoutingOnly));
    assert.ok(w.includes(OPS_DISCRETE_COPY.liftNotSameEvent));
    assert.ok(w.includes(OPS_DISCRETE_COPY.zeroNotProof));
    assert.ok(w.includes(OPS_DISCRETE_COPY.goldZeroUntilLabels));
    assert.ok(w.includes(OPS_DISCRETE_COPY.laddersNoGo));
  });

  it("throws if a forbidden field (score/same_event) is re-introduced", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_DISCRETE_FRONTIER, score: 0.9 }),
      /forbidden field: score/,
    );
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_DISCRETE_FRONTIER, extra: [{ same_event: true }] }),
      /forbidden field: same_event/,
    );
  });

  // ── ADR#80: live recall probe applied to ACTUAL pairs (aggregate only) ──
  it("surfaces live recall probe as aggregate only (status + max score + newly-routed; no per-pair score)", () => {
    const byLabel = Object.fromEntries(
      toR1DiscreteFrontierDisplayRows(SAMPLE_DISCRETE_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Live recall lift status"], "live_blocked_by_rate_or_opt_in");
    assert.equal(byLabel["Live recall probe max score (routing signal, not truth)"], "0");
    assert.equal(byLabel["Live pairs newly routed by probe (not same-event)"], "0");
  });

  it("displays a live_recall_lift_found state without asserting same-event (still no forbidden field)", () => {
    const lift = {
      ...SAMPLE_DISCRETE_FRONTIER,
      live_recall_lift_status: "live_recall_lift_found",
      live_frontier_verdict: "live_recall_lift_found",
      max_live_recall_probe_score: 0.3333,
      live_pairs_newly_routed_by_probe: 1,
      live_candidate_count: 1,
    };
    assert.doesNotThrow(() => assertOpsContractSafe(lift));
    const byLabel = Object.fromEntries(
      toR1DiscreteFrontierDisplayRows(lift).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Live recall lift status"], "live_recall_lift_found");
    assert.equal(byLabel["Live recall probe max score (routing signal, not truth)"], "0.3333");
    assert.equal(byLabel["Live pairs newly routed by probe (not same-event)"], "1");
    assert.ok(r1DiscreteFrontierWarnings(lift).includes(OPS_DISCRETE_COPY.newlyRoutedNotSameEvent));
  });

  it("warns: newly routed != same event + production gold remains 0", () => {
    const w = r1DiscreteFrontierWarnings(SAMPLE_DISCRETE_FRONTIER);
    assert.ok(w.includes(OPS_DISCRETE_COPY.newlyRoutedNotSameEvent));
    assert.ok(w.includes(OPS_DISCRETE_COPY.productionGoldZero));
  });
});

// ── ADR#81 provider breadth + named single-event seed + KO source path frontier — inline 재선언 lock ──
const OPS_BREADTH_COPY = {
  breadthSupportNotTruth: "Provider breadth is acquisition support, not truth",
  namedSeedNotProof: "Named seed is candidate generation, not same-event proof",
  communityNotAnchor: "Community reaction is not an event anchor",
  productionGoldZero: "Production gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
};

function toR1BreadthFrontierDisplayRows(f) {
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

function r1BreadthFrontierWarnings(f) {
  const out = [...(f.required_copy ?? [])];
  const ensure = (s) => {
    if (!out.includes(s)) out.push(s);
  };
  ensure(OPS_BREADTH_COPY.breadthSupportNotTruth);
  ensure(OPS_BREADTH_COPY.namedSeedNotProof);
  ensure(OPS_BREADTH_COPY.communityNotAnchor);
  ensure(OPS_BREADTH_COPY.productionGoldZero);
  if (f.r2_r7_no_go) ensure(OPS_BREADTH_COPY.laddersNoGo);
  return out;
}

const SAMPLE_BREADTH_FRONTIER = {
  contract: "InternalOpsProviderBreadthFrontier",
  provider_breadth_status: "ready_25_anchor_of_57",
  provider_breadth_inventory_ready: true,
  query_capable_provider_count: 7,
  feed_only_provider_count: 7,
  official_source_count: 5,
  search_url_candidate_count: 4,
  ko_official_news_count: 6,
  community_reaction_only_count: 9,
  market_signal_only_count: 6,
  catalog_enrichment_only_count: 9,
  unknown_quarantine_count: 4,
  anchor_eligible_count: 25,
  named_seed_bank_status: "ready_2_named_seeds",
  named_seed_count: 2,
  selected_seed_for_next_live_run: "fomc_rate_decision",
  seed_type: "named_single_event",
  ko_source_path_status: "ready_6_ko_news_live",
  ko_tokenization_risk_recorded: true,
  latest_live_seed: "fomc_decision",
  live_recall_lift_status: "live_blocked_by_rate_or_opt_in",
  max_live_recall_probe_score: 0.0,
  newly_routed_count: 0,
  production_candidate_status: "blocked_no_live_opt_in",
  blocked_reason: "blocked_no_live_opt_in",
  current_r1_gap: 200,
  r2_r7_no_go: true,
  acquisition_next_action: "confirm_actual_event_for_named_seed:fomc_rate_decision then request bounded live run (host/rate honored)",
  required_copy: [
    "Provider breadth is acquisition support, not truth",
    "Named seed is candidate generation, not same-event proof",
    "Community reaction is not an event anchor",
    "Production gold remains 0 until human labels are returned",
    "R2~R7 remain No-Go",
  ],
  flags: {
    no_public_truth: true, no_same_event_truth: true, no_score: true, no_rationale: true,
    no_predicted_status: true, no_raw_body: true, no_secret: true,
  },
};

describe("ADR#81 provider breadth + named seed + KO path frontier view", () => {
  it("passes the sanitized frontier contract (no forbidden fields)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_BREADTH_FRONTIER));
  });

  it("shows the 9-category provider breadth counts with non-anchor roles separated", () => {
    const byLabel = Object.fromEntries(
      toR1BreadthFrontierDisplayRows(SAMPLE_BREADTH_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Query-capable publishable providers"], "7");
    assert.equal(byLabel["Feed-only publishable providers"], "7");
    assert.equal(byLabel["KO official/news (anchor-eligible)"], "6");
    assert.equal(byLabel["Community (reaction-only, not anchor)"], "9");
    assert.equal(byLabel["Market (signal-only, not anchor)"], "6");
    assert.equal(byLabel["Catalog (enrichment-only, not anchor)"], "9");
    assert.equal(byLabel["Anchor-eligible sources"], "25");
  });

  it("labels search URL candidates as not truth until fetched", () => {
    const labels = toR1BreadthFrontierDisplayRows(SAMPLE_BREADTH_FRONTIER).map((r) => r.label);
    assert.ok(labels.includes("Search URL candidates (not truth until fetched)"));
  });

  it("shows named single-event seed bank status + selected seed + seed type", () => {
    const byLabel = Object.fromEntries(
      toR1BreadthFrontierDisplayRows(SAMPLE_BREADTH_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Named single-event seeds"], "2");
    assert.equal(byLabel["Selected seed for next live run"], "fomc_rate_decision");
    assert.equal(byLabel["Seed type"], "named_single_event");
  });

  it("shows KO source path status + tokenization risk recorded", () => {
    const byLabel = Object.fromEntries(
      toR1BreadthFrontierDisplayRows(SAMPLE_BREADTH_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["KO source path status"], "ready_6_ko_news_live");
    assert.equal(byLabel["KO tokenization risk recorded"], "true");
  });

  it("surfaces live recall as aggregate only (status + max score + newly-routed; no per-pair score)", () => {
    const byLabel = Object.fromEntries(
      toR1BreadthFrontierDisplayRows(SAMPLE_BREADTH_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Live recall lift status"], "live_blocked_by_rate_or_opt_in");
    assert.equal(byLabel["Live recall probe max score (routing signal, not truth)"], "0");
    assert.equal(byLabel["Live pairs newly routed (not same-event)"], "0");
  });

  it("emits only string values (no leaked objects)", () => {
    for (const row of toR1BreadthFrontierDisplayRows(SAMPLE_BREADTH_FRONTIER)) {
      assert.equal(typeof row.value, "string");
    }
  });

  it("warns: breadth=support not truth + named seed != proof + community != anchor + gold 0 + No-Go", () => {
    const w = r1BreadthFrontierWarnings(SAMPLE_BREADTH_FRONTIER);
    assert.ok(w.includes(OPS_BREADTH_COPY.breadthSupportNotTruth));
    assert.ok(w.includes(OPS_BREADTH_COPY.namedSeedNotProof));
    assert.ok(w.includes(OPS_BREADTH_COPY.communityNotAnchor));
    assert.ok(w.includes(OPS_BREADTH_COPY.productionGoldZero));
    assert.ok(w.includes(OPS_BREADTH_COPY.laddersNoGo));
  });

  it("throws if a forbidden field (score/same_event) is re-introduced", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_BREADTH_FRONTIER, score: 0.9 }),
      /forbidden field: score/,
    );
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_BREADTH_FRONTIER, extra: [{ same_event: true }] }),
      /forbidden field: same_event/,
    );
  });
});
