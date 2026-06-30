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

// ── ADR#82 bounded live breadth run + date-pin gate + production candidate freeze attempt frontier — inline lock ──
const OPS_BOUNDED_COPY = {
  breadthSupportNotTruth: "Provider breadth is acquisition support, not truth",
  namedSeedNotProof: "Named seed is candidate generation, not same-event proof",
  liveRunNeedsDatePin: "A bounded live run requires an operator-confirmed date-pinned event",
  communityNotAnchor: "Community reaction is not an event anchor",
  freezeNotTruth: "Production candidate freeze is a reviewer worklist, not same-event truth",
  productionGoldZero: "Production gold remains 0 until human labels are returned",
  laddersNoGo: "R2~R7 remain No-Go",
};

function toR1BoundedLiveBreadthFrontierDisplayRows(f) {
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

function r1BoundedLiveBreadthFrontierWarnings(f) {
  const out = [...(f.required_copy ?? [])];
  const ensure = (s) => {
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

const SAMPLE_BOUNDED_FRONTIER = {
  contract: "InternalOpsBoundedLiveBreadthFrontier",
  latest_bounded_live_run_status: "blocked_no_live_opt_in",
  named_seed_selected: "fomc_rate_decision",
  named_seed_date_pin_status: "not_pinned:missing_occurrence_date",
  selected_seed_actual_occurrence: null,
  live_query_approved: false,
  live_query_executed: false,
  live_call_count: 0,
  providers_used: [],
  provider_breadth_used: 2,
  key_free_provider_count: 0,
  credential_required_provider_count: 2,
  comparison_pair_count: 0,
  max_recall_probe_score: 0.0,
  newly_routed_count: 0,
  production_candidate_status: "blocked_no_live_opt_in",
  production_candidate_batch_ready: false,
  production_frozen_pair_count: 0,
  sanitized_snapshot_status: "not_written_no_live_run",
  ko_source_lane_status: "ready_5_keyfree_live_ko_news_anchors",
  ko_named_seed_needed: true,
  ko_floor_current: 0,
  ko_floor_required: 50,
  blocked_reason: "missing_date_pinned_named_event",
  acquisition_next_action:
    "provide_or_select_date_pinned_event then request bounded live run approval (host/rate honored · 1~2 seeds max)",
  current_r1_gap: 200,
  production_gold_count: 0,
  r2_r7_no_go: true,
  required_copy: [
    "Provider breadth is acquisition support, not truth",
    "Named seed is candidate generation, not same-event proof",
    "A bounded live run requires an operator-confirmed date-pinned event",
    "Community reaction is not an event anchor",
    "Production candidate freeze is a reviewer worklist, not same-event truth",
    "Production gold remains 0 until human labels are returned",
    "R2~R7 remain No-Go",
  ],
  flags: {
    no_public_truth: true, no_same_event_truth: true, no_score: true, no_rationale: true,
    no_predicted_status: true, no_raw_body: true, no_secret: true,
  },
};

describe("ADR#82 bounded live breadth run + date-pin gate + freeze attempt frontier view", () => {
  it("passes the sanitized frontier contract (no forbidden fields)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_BOUNDED_FRONTIER));
  });

  it("shows the named seed date-pin status as not pinned (missing occurrence date)", () => {
    const byLabel = Object.fromEntries(
      toR1BoundedLiveBreadthFrontierDisplayRows(SAMPLE_BOUNDED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Named seed selected"], "fomc_rate_decision");
    assert.equal(byLabel["Named seed date-pin status"], "not_pinned:missing_occurrence_date");
    assert.equal(byLabel["Selected seed actual occurrence"], "(not pinned)");
    assert.equal(byLabel["Blocked reason"], "missing_date_pinned_named_event");
  });

  it("shows the bounded live pool as adapter-wired ∩ credential (not breadth size)", () => {
    const byLabel = Object.fromEntries(
      toR1BoundedLiveBreadthFrontierDisplayRows(SAMPLE_BOUNDED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Provider breadth used (adapter-wired ∩ credential)"], "2");
    assert.equal(byLabel["Key-free providers in pool"], "0");
    assert.equal(byLabel["Credential-required providers in pool"], "2");
    assert.equal(byLabel["Providers used (actual)"], "(none)");
  });

  it("shows freeze status as blocked with 0 frozen pairs and gold 0 (no truth)", () => {
    const byLabel = Object.fromEntries(
      toR1BoundedLiveBreadthFrontierDisplayRows(SAMPLE_BOUNDED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Production candidate status"], "blocked_no_live_opt_in");
    assert.equal(byLabel["Production frozen pair count (worklist, not truth)"], "0");
    assert.equal(byLabel["Production gold count"], "0");
    assert.equal(byLabel["Sanitized snapshot status"], "not_written_no_live_run");
  });

  it("shows the KO source lane status + floor 0/50 + named seed needed", () => {
    const byLabel = Object.fromEntries(
      toR1BoundedLiveBreadthFrontierDisplayRows(SAMPLE_BOUNDED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["KO source lane status"], "ready_5_keyfree_live_ko_news_anchors");
    assert.equal(byLabel["KO named seed needed"], "true");
    assert.equal(byLabel["KO floor"], "0/50");
  });

  it("emits only string values (no leaked objects)", () => {
    for (const row of toR1BoundedLiveBreadthFrontierDisplayRows(SAMPLE_BOUNDED_FRONTIER)) {
      assert.equal(typeof row.value, "string");
    }
  });

  it("warns: breadth=support + named seed != proof + live run needs date-pin + freeze != truth + gold 0 + No-Go", () => {
    const w = r1BoundedLiveBreadthFrontierWarnings(SAMPLE_BOUNDED_FRONTIER);
    assert.ok(w.includes(OPS_BOUNDED_COPY.breadthSupportNotTruth));
    assert.ok(w.includes(OPS_BOUNDED_COPY.namedSeedNotProof));
    assert.ok(w.includes(OPS_BOUNDED_COPY.liveRunNeedsDatePin));
    assert.ok(w.includes(OPS_BOUNDED_COPY.communityNotAnchor));
    assert.ok(w.includes(OPS_BOUNDED_COPY.freezeNotTruth));
    assert.ok(w.includes(OPS_BOUNDED_COPY.productionGoldZero));
    assert.ok(w.includes(OPS_BOUNDED_COPY.laddersNoGo));
  });

  it("throws if a forbidden field (score/same_event) is re-introduced", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_BOUNDED_FRONTIER, score: 0.9 }),
      /forbidden field: score/,
    );
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_BOUNDED_FRONTIER, extra: [{ predicted_status: "merge" }] }),
      /forbidden field: predicted_status/,
    );
  });
});

// ── ADR#83 date-pinned live run frontier(inline-locked·opsPilotExecutionView.ts 와 동기화) ──
const OPS_DATE_PINNED_COPY = {
  operatorEventRequired: "A date-pinned operator event is required before any bounded live run",
  occurrenceIsAssertion: "occurrence_date is an operator assertion, not a code-verified fact",
  datePinNotOccurrence: "A date pin does not prove the event occurred or that both sources cover it",
  queryTargetsOperatorEvent: "The live query targets the operator event, never a curated seed fallback",
  operatorConfirmationRequired: "Operator confirmation is required before live regulatory acquisition",
  contactReadinessNotSending: "Reviewer contact readiness is not actual sending",
  payloadRequiredBeforeLive: "Provide an operator-confirmed regulatory event payload before live acquisition",
  dropboxNotGold: "Returned label dropbox readiness is not production gold",
  freezeNotTruth: "Production candidate freeze is a reviewer worklist, not same-event truth",
  productionGoldZero: "Production gold remains 0 until human labels are returned",
  communityStyleProduct: "This project targets a community-style intelligence web product, not a raw news feed",
  hotPostRuntimeDisabled: "Hot Intelligence Post runtime remains disabled until evidence, gold, and merge gates pass",
  communityReactionOnly: "Community reaction is reaction_to only, not an evidence anchor",
  realPayloadBeforeLive: "Operator must provide a real confirmed payload before live acquisition",
  liveNoYieldActionable: "Live no-yield results are actionable diagnostics, not failure endpoints",
  hotPostRequiresR1R2: "Hot Post public runtime requires R1/R2 gates",
  returnedLabelsNotGoldUntilAgreement: "Returned labels are not gold until agreement gates pass",
  laddersNoGo: "R2~R7 remain No-Go",
  liveAttemptPackDrafts: "Live attempt packs are drafts, not confirmed events",
  newsBreadthPlanning: "News breadth expansion is a planning recommendation, not a runtime change",
  freezeWorklistNotGold: "Freeze is a reviewer worklist only, not gold",
  firstContactManual: "Reviewer first contact is manual; the system never sends labels or messages",
  hotPostPreviewInternalOnly: "Hot Post preview is internal-only and cannot be published before R1/R2 gates",
  liveAttemptPackManualVerify: "Live attempt packs must be manually verified before becoming real payloads",
  validateDryRunNoLive: "Validate-only and dry-run do not call live providers",
  liveRunRequiresApproved: "Live run requires operator-confirmed payload and live_approved=true",
  returnedLabelsValidationAgreement: "Returned labels require validation and agreement before R1 gold",
  communityFeedbackFutureOnly: "Community feedback loop is future contract only; comment runtime is disabled",
};

function toR1DatePinnedLiveRunFrontierDisplayRows(f) {
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
    { label: "Provider date-window fidelity status", value: f.provider_date_window_fidelity_status },
    { label: "Control experiment status", value: f.control_experiment_status },
    { label: "Date-filter mechanism (hypothesis, not asserted)", value: f.date_filter_mechanism_primary },
    { label: "Mechanism confidence (never high from one run)", value: f.date_filter_mechanism_confidence },
    { label: "Out-of-window records dropped", value: `${f.out_of_window_records_dropped}` },
    { label: "Window-honoring source status", value: f.window_honoring_source_status },
    { label: "Federal Register adapter (official, not news)", value: f.federal_register_adapter_status },
    { label: "Federal Register live status", value: f.federal_register_live_status },
    { label: "FR date-filter capability (live-verified honoring)", value: f.federal_register_date_filter_capability },
    { label: "Official×news bridge status (routing only, not truth)", value: f.official_news_bridge_status },
    { label: "Official records (in-window)", value: `${f.official_records_count}` },
    { label: "News records (for bridge)", value: `${f.news_records_count}` },
    { label: "Official×news bridge candidates (not same-event)", value: `${f.bridge_candidate_count}` },
    { label: "Bridge freeze-eligible (in-window both)", value: `${f.official_news_freeze_eligible_count}` },
    { label: "Regulatory seed bank status", value: f.regulatory_seed_bank_status },
    { label: "Selected regulatory seed", value: f.selected_regulatory_seed_id ?? "(none)" },
    { label: "Official×news live status", value: f.official_news_live_status },
    { label: "Official×news production candidate (worklist, not truth)", value: f.official_news_production_candidate_status },
    { label: "Official×news reviewer handoff ready (no sending)", value: String(f.official_news_reviewer_handoff_ready) },
    { label: "Operator event status (gate, not truth)", value: f.operator_event_status },
    { label: "Operator confirmed (live-run approval, not same-event)", value: String(f.operator_confirmed) },
    { label: "Operator confirmation valid", value: String(f.confirmation_valid) },
    { label: "Confirmation blocked reason", value: f.confirmation_blocked_reason || "(none)" },
    { label: "Reviewer contact ready (readiness ≠ actual sending)", value: String(f.reviewer_contact_ready) },
    { label: "Official×news label intake readiness (synthetic dry-run)", value: f.label_intake_readiness_status },
    { label: "Operator payload status (real gitignored / example template)", value: f.operator_payload_status },
    { label: "Operator payload path status (where to drop the real payload)", value: f.operator_payload_path_status },
    { label: "Returned label dropbox ready (readiness ≠ production gold)", value: String(f.label_dropbox_ready) },
    { label: "Actual returned label count (real files only)", value: `${f.actual_returned_label_count}` },
    { label: "Reviewer contact launch checklist ready (not actual sending)", value: String(f.reviewer_contact_checklist_ready) },
    { label: "Operator payload template ready (authoring helper)", value: String(f.operator_payload_template_ready) },
    { label: "Operator payload next action", value: f.operator_payload_next_action },
    { label: "Live no-yield taxonomy status", value: f.live_no_yield_taxonomy_status },
    { label: "Hot Intelligence Post contract (runtime disabled)", value: f.hot_intelligence_post_contract_status },
    { label: "Agent hotness reasoning contract (runtime disabled)", value: f.agent_hotness_contract_status },
    { label: "Community interaction gate (runtime disabled)", value: f.community_interaction_gate_status },
    { label: "Operator payload sourcing status", value: f.payload_sourcing_status },
    { label: "Payload sourcing next action", value: f.payload_sourcing_next_action },
    { label: "Live no-yield taxonomy next action", value: f.taxonomy_next_action },
    { label: "Official×news overlap diagnostic status", value: f.overlap_diagnostic_status },
    { label: "Overlap blocked dimension", value: f.overlap_blocked_dimension || "(none)" },
    { label: "R1 label return status", value: f.r1_label_return_status },
    { label: "R1 label return next action", value: f.r1_label_return_next_action },
    { label: "Hot Post gate alignment status", value: f.hot_post_gate_status },
    { label: "Hot Post public readiness (requires R1/R2)", value: String(f.hot_post_public_readiness) },
    { label: "Community posting roadmap status (runtime disabled)", value: f.community_posting_roadmap_status },
    { label: "Live attempt pack status", value: f.live_attempt_pack_status },
    { label: "Live attempt pack next action", value: f.live_attempt_pack_next_action },
    { label: "News breadth trigger status", value: f.news_breadth_trigger_status },
    { label: "Recommended provider expansion (planning only)", value: f.recommended_provider_expansion || "(none)" },
    { label: "First freeze package hardening status", value: f.freeze_package_hardening_status },
    { label: "Freeze artifact reviewer-safe", value: String(f.freeze_artifact_safe) },
    { label: "R1 first-contact protocol status", value: f.r1_first_contact_protocol_status },
    { label: "R1 first-contact next action", value: f.r1_first_contact_next_action },
    { label: "Hot Post preview status (internal-only)", value: f.hot_post_preview_status },
    { label: "Hot Post preview public blocked", value: String(f.hot_post_preview_public_blocked) },
    { label: "Real payload promotion status (draft-only)", value: f.real_payload_promotion_status },
    { label: "Real payload promotion next action", value: f.real_payload_promotion_next_action },
    { label: "Operator live command pack status", value: f.operator_live_command_pack_status },
    { label: "Validate-only command ready (no network)", value: String(f.validate_payload_command_ready) },
    { label: "Dry-run command ready (no live network)", value: String(f.dry_run_command_ready) },
    { label: "Live-run command ready (requires approval)", value: String(f.live_run_command_ready) },
    { label: "Expected provider calls", value: `${f.expected_provider_calls}` },
    { label: "Real payload present", value: String(f.real_payload_present) },
    { label: "Real payload valid", value: String(f.real_payload_valid) },
    { label: "Freeze→R1 executable checklist status", value: f.freeze_to_r1_status },
    { label: "Label validation command ready", value: String(f.label_validation_command_ready) },
    { label: "Label intake command ready", value: String(f.label_intake_command_ready) },
    { label: "Agreement check command ready", value: String(f.agreement_check_command_ready) },
    { label: "Hot Post activation map status (runtime disabled)", value: f.hot_post_activation_map_status },
    { label: "Community feedback loop status (runtime disabled)", value: f.community_feedback_loop_status },
    { label: "Next provider expansion status (planning only)", value: f.next_provider_expansion_status },
    { label: "First real payload execution sprint status", value: f.first_real_payload_sprint_status },
    { label: "Operator-confirmed-ready package status", value: f.operator_confirmed_ready_package_status },
    { label: "Unified live result closure status (diagnostic)", value: f.unified_live_closure_status },
    { label: "Freeze→R1 dry-run status (synthetic)", value: f.freeze_r1_dry_run_status },
    { label: "ai_replies guard audit status", value: f.ai_replies_guard_audit_status },
    { label: "Public runtime kill-switch status (all disabled)", value: f.public_runtime_kill_switch_status },
    { label: "Source graph/time-series contract status (candidate)", value: f.source_graph_timeseries_contract_status },
    { label: "Evidence-assisted payload production kit status", value: f.evidence_payload_kit_status },
    { label: "Operator verification worksheet status", value: f.operator_verification_worksheet_status },
    { label: "Real payload file template hardening status", value: f.payload_template_hardening_status },
    { label: "First payload candidate evidence binder status", value: f.first_payload_evidence_binder_status },
    { label: "Reviewer packet dry-run status (synthetic)", value: f.reviewer_packet_dry_run_status },
    { label: "ai_replies gate design status (runtime disabled)", value: f.ai_replies_gate_design_status },
    { label: "Source graph Hot Post integration map status (candidate)", value: f.source_graph_hot_post_integration_status },
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

function r1DatePinnedLiveRunFrontierWarnings(f) {
  const out = [...(f.required_copy ?? [])];
  const ensure = (s) => {
    if (!out.includes(s)) out.push(s);
  };
  ensure(OPS_DATE_PINNED_COPY.operatorEventRequired);
  ensure(OPS_DATE_PINNED_COPY.occurrenceIsAssertion);
  ensure(OPS_DATE_PINNED_COPY.datePinNotOccurrence);
  ensure(OPS_DATE_PINNED_COPY.queryTargetsOperatorEvent);
  ensure(OPS_DATE_PINNED_COPY.operatorConfirmationRequired);
  ensure(OPS_DATE_PINNED_COPY.contactReadinessNotSending);
  ensure(OPS_DATE_PINNED_COPY.payloadRequiredBeforeLive);
  ensure(OPS_DATE_PINNED_COPY.dropboxNotGold);
  ensure(OPS_DATE_PINNED_COPY.freezeNotTruth);
  ensure(OPS_DATE_PINNED_COPY.productionGoldZero);
  ensure(OPS_DATE_PINNED_COPY.communityStyleProduct);
  ensure(OPS_DATE_PINNED_COPY.hotPostRuntimeDisabled);
  ensure(OPS_DATE_PINNED_COPY.communityReactionOnly);
  ensure(OPS_DATE_PINNED_COPY.realPayloadBeforeLive);
  ensure(OPS_DATE_PINNED_COPY.liveNoYieldActionable);
  ensure(OPS_DATE_PINNED_COPY.hotPostRequiresR1R2);
  ensure(OPS_DATE_PINNED_COPY.returnedLabelsNotGoldUntilAgreement);
  // ADR#92 — live attempt pack + news breadth + freeze hardening + first-contact + preview copy.
  ensure(OPS_DATE_PINNED_COPY.liveAttemptPackDrafts);
  ensure(OPS_DATE_PINNED_COPY.newsBreadthPlanning);
  ensure(OPS_DATE_PINNED_COPY.freezeWorklistNotGold);
  ensure(OPS_DATE_PINNED_COPY.firstContactManual);
  ensure(OPS_DATE_PINNED_COPY.hotPostPreviewInternalOnly);
  // ADR#93 — real payload promotion + operator live command pack + freeze→R1 + activation map + feedback loop copy.
  ensure(OPS_DATE_PINNED_COPY.liveAttemptPackManualVerify);
  ensure(OPS_DATE_PINNED_COPY.validateDryRunNoLive);
  ensure(OPS_DATE_PINNED_COPY.liveRunRequiresApproved);
  ensure(OPS_DATE_PINNED_COPY.returnedLabelsValidationAgreement);
  ensure(OPS_DATE_PINNED_COPY.communityFeedbackFutureOnly);
  if (f.r2_r7_no_go) ensure(OPS_DATE_PINNED_COPY.laddersNoGo);
  return out;
}

const SAMPLE_DATE_PINNED_FRONTIER = {
  contract: "InternalOpsDatePinnedLiveRunFrontier",
  latest_date_pinned_live_run_status: "missing_operator_date_pinned_event",
  operator_event_provided: false,
  occurrence_date: null,
  occurrence_date_valid_iso: false,
  date_pinned_named_event_valid: false,
  live_query_target_wired: true,
  live_query_approved: false,
  live_query_executed: false,
  live_call_count: 0,
  providers_used: [],
  comparison_pair_count: 0,
  max_recall_probe_score: 0.0,
  newly_routed_count: 0,
  production_candidate_status: "blocked",
  production_candidate_batch_ready: false,
  production_frozen_pair_count: 0,
  candidate_provenance: "none",
  sanitized_snapshot_status: "not_written_no_live_run",
  date_window_enforced: false,
  reviewer_handoff_ready: false,
  provider_date_window_fidelity_status: "control_experiment_pending",
  control_experiment_status: "not_run",
  date_filter_mechanism_primary: "undetermined",
  date_filter_mechanism_confidence: "none",
  out_of_window_records_dropped: 0,
  window_honoring_source_status: "federal_register_adapter_wired",
  federal_register_adapter_status: "wired",
  federal_register_live_status: "not_run",
  federal_register_date_filter_capability: "documented_unverified",
  official_news_bridge_status: "bridge_built_not_run",
  official_records_count: 0,
  news_records_count: 0,
  bridge_candidate_count: 0,
  official_news_freeze_eligible_count: 0,
  regulatory_seed_bank_status: "ready",
  selected_regulatory_seed_id: "epa_final_rule_emissions",
  official_news_live_status: "not_run",
  official_news_production_candidate_status: "blocked",
  official_news_reviewer_handoff_ready: false,
  operator_event_status: "not_provided",
  operator_confirmed: false,
  confirmation_valid: false,
  confirmation_blocked_reason: "operator_event_not_provided",
  reviewer_contact_ready: false,
  label_intake_readiness_status: "official_news_label_intake_dry_run_ready",
  operator_payload_status: "not_provided",
  operator_payload_path_status: "example_only_no_real_payload",
  label_dropbox_ready: true,
  actual_returned_label_count: 0,
  reviewer_contact_checklist_ready: false,
  operator_payload_template_ready: true,
  operator_payload_next_action:
    "fill the missing fields in the template, then save it to inputs/operator_events/operator_regulatory_event_payload.json",
  live_no_yield_taxonomy_status: "missing_payload",
  hot_intelligence_post_contract_status: "contract_ready_runtime_disabled",
  agent_hotness_contract_status: "contract_ready_runtime_disabled",
  community_interaction_gate_status: "community_interaction_requirements_unmet",
  payload_sourcing_status: "real_payload_absent_template_ready",
  payload_sourcing_next_action:
    "author the payload from the template, save it to inputs/operator_events/operator_regulatory_event_payload.json (gitignored), validate with live_approved=false, then confirm + approve and run the live command — no real payload is present yet",
  taxonomy_next_action: "author and drop a real operator payload (use the authoring helper), then approve a live run",
  overlap_diagnostic_status: "not_run",
  overlap_blocked_dimension: "",
  r1_label_return_status: "awaiting_returned_labels",
  r1_label_return_next_action:
    "no returned labels yet — distribute the handoff bundle manually, place returned JSONL in the gitignored intake directory, then run the intake command",
  hot_post_gate_status: "blocked_requirements_unmet",
  hot_post_public_readiness: false,
  community_posting_roadmap_status: "community_posting_roadmap_defined_runtime_disabled",
  live_attempt_pack_status: "live_attempt_pack_ready_operator_fill_required",
  live_attempt_pack_next_action:
    "no real payload is present yet — pick one of the 4 candidate event shapes, confirm the event actually occurred, fill the payload template, save it to inputs/operator_events/operator_regulatory_event_payload.json (gitignored), then validate (live_approved=false), set operator_confirmed=true ∧ live_approved=true, and run the manual live command",
  news_breadth_trigger_status: "no_news_side_gap_not_triggered",
  recommended_provider_expansion: "",
  freeze_package_hardening_status: "no_freeze_artifact_to_harden",
  freeze_artifact_safe: false,
  r1_first_contact_protocol_status: "protocol_defined_awaiting_freeze",
  r1_first_contact_next_action:
    "no production-candidate freeze yet — acquire in-window official×news pairs, freeze, and harden the worklist (first_freeze_package_hardening) before first contact",
  hot_post_preview_status: "preview_blocked_fix_draft",
  hot_post_preview_public_blocked: true,
  real_payload_promotion_status: "promotion_draft_ready_operator_must_confirm",
  real_payload_promotion_next_action:
    "the selected attempt candidate is a DRAFT, not a confirmed event — verify the event actually occurred first, then set operator_confirmed=true ∧ live_approved=true, save to inputs/operator_events/ (gitignored), and run the manual live command",
  operator_live_command_pack_status: "command_pack_ready_no_event_template_only",
  validate_payload_command_ready: true,
  dry_run_command_ready: true,
  live_run_command_ready: true,
  expected_provider_calls: 3,
  real_payload_present: false,
  real_payload_valid: false,
  freeze_to_r1_status: "blocked_no_production_candidate_freeze",
  label_validation_command_ready: false,
  label_intake_command_ready: false,
  agreement_check_command_ready: false,
  hot_post_activation_map_status: "hot_post_activation_map_defined_runtime_disabled",
  community_feedback_loop_status: "community_feedback_loop_defined_runtime_disabled",
  next_provider_expansion_status: "no_expansion_recommended",
  first_real_payload_sprint_status: "awaiting_operator_payload",
  operator_confirmed_ready_package_status: "operator_confirmed_ready_package_ready",
  unified_live_closure_status: "closed_missing_payload",
  freeze_r1_dry_run_status: "synthetic_freeze_r1_dry_run_ready",
  ai_replies_guard_audit_status: "ungated_mock_endpoint_detected",
  public_runtime_kill_switch_status: "public_runtime_kill_switch_all_disabled",
  source_graph_timeseries_contract_status: "candidate_only_runtime_disabled",
  evidence_payload_kit_status: "evidence_payload_kit_ready",
  operator_verification_worksheet_status: "worksheet_incomplete_operator_must_verify",
  payload_template_hardening_status: "payload_template_hardened",
  first_payload_evidence_binder_status: "evidence_binder_ready",
  reviewer_packet_dry_run_status: "synthetic_reviewer_packet_dry_run_ready",
  ai_replies_gate_design_status: "gate_design_blocked_required_gate_missing",
  source_graph_hot_post_integration_status: "integration_map_candidate_only_runtime_disabled",
  ko_source_lane_status: "ready_5_keyfree_live_ko_news_anchors",
  ko_named_seed_needed: true,
  ko_floor_current: 0,
  ko_floor_required: 50,
  blocked_reason: "missing_operator_date_pinned_event",
  acquisition_next_action:
    "operator must provide a date-pinned event (named_entity + event_phrase + occurrence_date ISO)",
  current_r1_gap: 200,
  production_gold_count: 0,
  r2_r7_no_go: true,
  required_copy: [
    "A date-pinned operator event is required before any bounded live run",
    "occurrence_date is an operator assertion, not a code-verified fact",
    "A date pin does not prove the event occurred or that both sources cover it",
    "The live query targets the operator event, never a curated seed fallback",
    "Provider date parameters are not trusted until verified by a control experiment",
    "Out-of-window records cannot become production candidates",
    "Federal Register is official evidence, not a news article",
    "Official-news bridge is reviewer-routing only, not same-event truth",
    "Official record alone is not a production cross-source candidate",
    "A regulatory-class seed needs an agency/entity, an action, and a confirmed date window",
    "Operator confirmation is required before live regulatory acquisition",
    "Reviewer contact readiness is not actual sending",
    "Provide an operator-confirmed regulatory event payload before live acquisition",
    "Returned label dropbox readiness is not production gold",
    "Production candidate freeze is a reviewer worklist, not same-event truth",
    "Production gold remains 0 until human labels are returned",
    "This project targets a community-style intelligence web product, not a raw news feed",
    "Hot Intelligence Post runtime remains disabled until evidence, gold, and merge gates pass",
    "Community reaction is reaction_to only, not an evidence anchor",
    "Operator must provide a real confirmed payload before live acquisition",
    "Live no-yield results are actionable diagnostics, not failure endpoints",
    "Hot Post public runtime requires R1/R2 gates",
    "Returned labels are not gold until agreement gates pass",
    "R2~R7 remain No-Go",
    "Live attempt packs are drafts, not confirmed events",
    "News breadth expansion is a planning recommendation, not a runtime change",
    "Freeze is a reviewer worklist only, not gold",
    "Reviewer first contact is manual; the system never sends labels or messages",
    "Hot Post preview is internal-only and cannot be published before R1/R2 gates",
    "Live attempt packs must be manually verified before becoming real payloads",
    "Validate-only and dry-run do not call live providers",
    "Live run requires operator-confirmed payload and live_approved=true",
    "Returned labels require validation and agreement before R1 gold",
    "Community feedback loop is future contract only; comment runtime is disabled",
  ],
  flags: {
    no_public_truth: true, no_same_event_truth: true, no_score: true, no_rationale: true,
    no_predicted_status: true, no_raw_body: true, no_secret: true,
  },
};

describe("ADR#83 date-pinned live query plumbing + bounded live run + freeze frontier view", () => {
  it("passes the sanitized frontier contract (no forbidden fields)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_DATE_PINNED_FRONTIER));
  });

  it("shows operator event not provided + occurrence not provided + blocked reason", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Operator event provided"], "false");
    assert.equal(byLabel["Occurrence date (operator assertion, unverified)"], "(not provided)");
    assert.equal(byLabel["Date-pinned named event valid"], "false");
    assert.equal(byLabel["Blocked reason"], "missing_operator_date_pinned_event");
  });

  it("shows the live query target wired (test-locked) but live not executed (no opt-in)", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Live query target wired"], "true");
    assert.equal(byLabel["Live query executed"], "false");
    assert.equal(byLabel["Providers used (actual)"], "(none)");
  });

  it("shows freeze status blocked with 0 frozen pairs, provenance none, gold 0 (no truth)", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Production candidate status"], "blocked");
    assert.equal(byLabel["Production frozen pair count (worklist, not truth)"], "0");
    assert.equal(byLabel["Candidate provenance"], "none");
    assert.equal(byLabel["Production gold count"], "0");
  });

  it("shows the KO source lane status + floor 0/50 + named seed needed", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["KO source lane status"], "ready_5_keyfree_live_ko_news_anchors");
    assert.equal(byLabel["KO named seed needed"], "true");
    assert.equal(byLabel["KO floor"], "0/50");
  });

  it("emits only string values (no leaked objects)", () => {
    for (const row of toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER)) {
      assert.equal(typeof row.value, "string");
    }
  });

  it("(ADR#84) shows date window enforced + reviewer handoff readiness (no live → both false)", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Date window enforced (out-of-window dropped)"], "false");
    assert.equal(byLabel["Reviewer handoff ready (pre-contact; no sending)"], "false");
  });

  it("(ADR#85) shows date-window fidelity control experiment status + mechanism (hypothesis, not asserted) + window-honoring source", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // control experiment 미실행 → pending/not_run·메커니즘 미확정(절대 단정 0).
    assert.equal(byLabel["Provider date-window fidelity status"], "control_experiment_pending");
    assert.equal(byLabel["Control experiment status"], "not_run");
    assert.equal(byLabel["Date-filter mechanism (hypothesis, not asserted)"], "undetermined");
    assert.equal(byLabel["Mechanism confidence (never high from one run)"], "none");
    assert.notEqual(byLabel["Mechanism confidence (never high from one run)"], "high");
    // window-honoring hedge: Federal Register adapter 배선됨(ADR#86 — recommended→wired).
    assert.equal(byLabel["Window-honoring source status"], "federal_register_adapter_wired");
    assert.equal(byLabel["Out-of-window records dropped"], "0");
  });

  it("(ADR#86) shows Federal Register official adapter wired + official×news bridge (routing only, not truth)", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // FR=official 증거(news 아님)·adapter 배선됨. live 미실행이면 not_run·date_filter 는 documented_unverified.
    assert.equal(byLabel["Federal Register adapter (official, not news)"], "wired");
    assert.equal(byLabel["Federal Register live status"], "not_run");
    assert.equal(byLabel["FR date-filter capability (live-verified honoring)"], "documented_unverified");
    // official×news bridge=reviewer-routing only(same-event truth 아님)·official 단독 freeze 금지.
    assert.equal(byLabel["Official×news bridge status (routing only, not truth)"], "bridge_built_not_run");
    assert.equal(byLabel["Official×news bridge candidates (not same-event)"], "0");
    assert.equal(byLabel["Bridge freeze-eligible (in-window both)"], "0");
  });

  it("(ADR#86) warns: Federal Register is official evidence + official-news bridge is routing only", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes("Federal Register is official evidence, not a news article"));
    assert.ok(w.includes("Official-news bridge is reviewer-routing only, not same-event truth"));
  });

  it("(ADR#87) shows regulatory seed bank ready + selected seed + official×news live status (not run, no opt-in)", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // regulatory seed bank=official×news 동시 포착 가능 event shape(network 0·항상 ready). selected seed 노출.
    assert.equal(byLabel["Regulatory seed bank status"], "ready");
    assert.equal(byLabel["Selected regulatory seed"], "epa_final_rule_emissions");
    // official×news live=fetch→bridge→freeze 분류(미실행이면 not_run)·production candidate=worklist(truth 아님)·handoff 미준비.
    assert.equal(byLabel["Official×news live status"], "not_run");
    assert.equal(byLabel["Official×news production candidate (worklist, not truth)"], "blocked");
    assert.equal(byLabel["Official×news reviewer handoff ready (no sending)"], "false");
  });

  it("(ADR#87) reflects a frozen official×news live run (worklist ready, handoff ready, no sending/gold)", () => {
    const frozen = {
      ...SAMPLE_DATE_PINNED_FRONTIER,
      official_news_live_status: "production_batch_frozen",
      official_news_production_candidate_status: "production_batch_frozen",
      official_news_reviewer_handoff_ready: true,
      federal_register_live_status: "fr_live_ok_in_window",
      federal_register_date_filter_capability: "live_verified",
      bridge_candidate_count: 1,
      official_news_freeze_eligible_count: 1,
    };
    // 동결 상태여도 contract 안전(forbidden 0)·production gold 0(worklist≠truth).
    assert.doesNotThrow(() => assertOpsContractSafe(frozen));
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(frozen).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Official×news live status"], "production_batch_frozen");
    assert.equal(byLabel["Official×news reviewer handoff ready (no sending)"], "true");
    assert.equal(byLabel["Production gold count"], "0");
  });

  it("(ADR#87) warns: official record alone is not a cross-source candidate + regulatory seed needs agency/action/date", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes("Official record alone is not a production cross-source candidate"));
    assert.ok(
      w.includes("A regulatory-class seed needs an agency/entity, an action, and a confirmed date window"),
    );
  });

  it("warns: operator event required + occurrence=assertion + date-pin != occurrence + query targets operator event + freeze != truth + gold 0 + No-Go", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.operatorEventRequired));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.occurrenceIsAssertion));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.datePinNotOccurrence));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.queryTargetsOperatorEvent));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.freezeNotTruth));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.productionGoldZero));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.laddersNoGo));
  });

  it("throws if a forbidden field (score/same_event) is re-introduced", () => {
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_DATE_PINNED_FRONTIER, score: 0.9 }),
      /forbidden field: score/,
    );
    assert.throws(
      () => assertOpsContractSafe({ ...SAMPLE_DATE_PINNED_FRONTIER, extra: [{ same_event: true }] }),
      /forbidden field: same_event/,
    );
  });

  it("(ADR#88) shows operator event not provided + contact not ready + label intake dry-run ready", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // operator confirmation 은 게이트(truth 아님)·미제공이면 not_provided. contact readiness 는 freeze 없음 → false.
    assert.equal(byLabel["Operator event status (gate, not truth)"], "not_provided");
    assert.equal(byLabel["Operator confirmed (live-run approval, not same-event)"], "false");
    assert.equal(byLabel["Operator confirmation valid"], "false");
    assert.equal(byLabel["Reviewer contact ready (readiness ≠ actual sending)"], "false");
    // label intake readiness 는 network 0·항상 synthetic dry-run ready(production gold 0).
    assert.equal(
      byLabel["Official×news label intake readiness (synthetic dry-run)"],
      "official_news_label_intake_dry_run_ready",
    );
  });

  it("(ADR#88) reflects a confirmed operator event with contact readiness (still no sending)", () => {
    const confirmed = {
      ...SAMPLE_DATE_PINNED_FRONTIER,
      operator_event_status: "confirmed_live_executed",
      operator_confirmed: true,
      confirmation_valid: true,
      confirmation_blocked_reason: "",
      reviewer_contact_ready: true,
    };
    assert.doesNotThrow(() => assertOpsContractSafe(confirmed));
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(confirmed).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Operator event status (gate, not truth)"], "confirmed_live_executed");
    assert.equal(byLabel["Operator confirmed (live-run approval, not same-event)"], "true");
    assert.equal(byLabel["Reviewer contact ready (readiness ≠ actual sending)"], "true");
    assert.equal(byLabel["Confirmation blocked reason"], "(none)");
  });

  it("(ADR#88) warns: operator confirmation required + reviewer contact readiness is not actual sending", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.operatorConfirmationRequired));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.contactReadinessNotSending));
  });

  it("(ADR#89) shows operator payload not provided + dropbox ready (not gold) + checklist not ready", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // operator payload=real(gitignored)/example 분리·미제공이면 not_provided·example_only. dropbox readiness=수신
    // 경로/schema 준비(실 label 전까지 production gold 0). contact launch checklist 는 freeze 없음 → 미준비.
    assert.equal(byLabel["Operator payload status (real gitignored / example template)"], "not_provided");
    assert.equal(
      byLabel["Operator payload path status (where to drop the real payload)"],
      "example_only_no_real_payload",
    );
    assert.equal(byLabel["Returned label dropbox ready (readiness ≠ production gold)"], "true");
    assert.equal(byLabel["Actual returned label count (real files only)"], "0");
    assert.equal(byLabel["Reviewer contact launch checklist ready (not actual sending)"], "false");
  });

  it("(ADR#89) reflects a present real payload + launch checklist ready (still no sending/gold)", () => {
    const ready = {
      ...SAMPLE_DATE_PINNED_FRONTIER,
      operator_payload_status: "present_valid_json",
      operator_payload_path_status: "real_payload_present",
      reviewer_contact_checklist_ready: true,
    };
    assert.doesNotThrow(() => assertOpsContractSafe(ready));
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(ready).map((r) => [r.label, r.value]),
    );
    assert.equal(byLabel["Operator payload status (real gitignored / example template)"], "present_valid_json");
    assert.equal(byLabel["Reviewer contact launch checklist ready (not actual sending)"], "true");
    assert.equal(byLabel["Production gold count"], "0");
  });

  it("(ADR#89) warns: operator payload required before live + returned label dropbox readiness is not production gold", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.payloadRequiredBeforeLive));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.dropboxNotGold));
  });

  it("(ADR#90) shows payload authoring template ready + live no-yield taxonomy + runtime-disabled contracts", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // payload 미제공이어도 authoring helper 가 fillable 템플릿을 준비(operator next action), no-yield 는 missing_payload.
    assert.equal(byLabel["Operator payload template ready (authoring helper)"], "true");
    assert.equal(byLabel["Live no-yield taxonomy status"], "missing_payload");
    // Hot Post / hotness / community gate 는 전부 runtime-disabled contract(public post·comment runtime No-Go).
    assert.equal(byLabel["Hot Intelligence Post contract (runtime disabled)"], "contract_ready_runtime_disabled");
    assert.equal(byLabel["Agent hotness reasoning contract (runtime disabled)"], "contract_ready_runtime_disabled");
    assert.equal(
      byLabel["Community interaction gate (runtime disabled)"],
      "community_interaction_requirements_unmet",
    );
  });

  it("(ADR#90) warns: community-style product + Hot Post runtime disabled + community reaction is reaction_to only", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.communityStyleProduct));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.hotPostRuntimeDisabled));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.communityReactionOnly));
  });

  it("(ADR#90) keeps the date-pinned frontier sanitized with the 6 ADR#90 fields (no forbidden keys)", () => {
    // ADR#90 6필드가 추가돼도 forbidden-key 가드를 통과한다(score/same_event/raw body/PII 미노출).
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_DATE_PINNED_FRONTIER));
    for (const k of [
      "operator_payload_template_ready", "operator_payload_next_action", "live_no_yield_taxonomy_status",
      "hot_intelligence_post_contract_status", "agent_hotness_contract_status", "community_interaction_gate_status",
    ]) {
      assert.ok(k in SAMPLE_DATE_PINNED_FRONTIER, `missing ${k}`);
    }
  });

  it("(ADR#91) shows sourcing status + overlap not_run + R1 label-return awaiting + hot-post blocked + roadmap runtime-disabled", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // payload 미제공 → sourcing 은 템플릿 작성 절차를 안내(real path 부재).
    assert.equal(byLabel["Operator payload sourcing status"], "real_payload_absent_template_ready");
    // live 미실행 → overlap 진단 not_run·blocked dimension 없음.
    assert.equal(byLabel["Official×news overlap diagnostic status"], "not_run");
    assert.equal(byLabel["Overlap blocked dimension"], "(none)");
    // returned label 0 → R1 label-return 은 awaiting(intake_command 대기).
    assert.equal(byLabel["R1 label return status"], "awaiting_returned_labels");
    // Hot Post gate 는 gold/merge/evidence 미충족 → blocked·public readiness false(runtime No-Go).
    assert.equal(byLabel["Hot Post gate alignment status"], "blocked_requirements_unmet");
    assert.equal(byLabel["Hot Post public readiness (requires R1/R2)"], "false");
    // community posting roadmap 은 정의됐으나 runtime disabled.
    assert.equal(
      byLabel["Community posting roadmap status (runtime disabled)"],
      "community_posting_roadmap_defined_runtime_disabled",
    );
  });

  it("(ADR#91) warns: real payload before live + no-yield is actionable + Hot Post requires R1/R2 + labels not gold until agreement", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.realPayloadBeforeLive));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.liveNoYieldActionable));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.hotPostRequiresR1R2));
    assert.ok(w.includes(OPS_DATE_PINNED_COPY.returnedLabelsNotGoldUntilAgreement));
  });

  it("(ADR#91) keeps the date-pinned frontier sanitized with the 10 ADR#91 fields (no forbidden keys)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_DATE_PINNED_FRONTIER));
    for (const k of [
      "payload_sourcing_status", "payload_sourcing_next_action", "taxonomy_next_action",
      "overlap_diagnostic_status", "overlap_blocked_dimension", "r1_label_return_status",
      "r1_label_return_next_action", "hot_post_gate_status", "hot_post_public_readiness",
      "community_posting_roadmap_status",
    ]) {
      assert.ok(k in SAMPLE_DATE_PINNED_FRONTIER, `missing ${k}`);
    }
  });

  it("(ADR#92) shows live attempt pack ready + news breadth not triggered + freeze no-artifact + first-contact awaiting + preview blocked", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // payload 미제공 → live attempt pack 은 operator 가 채울 후보 묶음 준비. 실행 0 이라 trigger 미발동.
    assert.equal(byLabel["Live attempt pack status"], "live_attempt_pack_ready_operator_fill_required");
    assert.equal(byLabel["News breadth trigger status"], "no_news_side_gap_not_triggered");
    // freeze 0 → no_artifact·safe=false. first-contact 는 freeze 대기. preview 는 빈 draft → blocked(public 항상 차단).
    assert.equal(byLabel["First freeze package hardening status"], "no_freeze_artifact_to_harden");
    assert.equal(byLabel["Freeze artifact reviewer-safe"], "false");
    assert.equal(byLabel["R1 first-contact protocol status"], "protocol_defined_awaiting_freeze");
    assert.equal(byLabel["Hot Post preview status (internal-only)"], "preview_blocked_fix_draft");
    assert.equal(byLabel["Hot Post preview public blocked"], "true");
  });

  it("(ADR#92) warns: live attempt packs are drafts + freeze is worklist not gold + first contact is manual + preview internal-only", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes("Live attempt packs are drafts, not confirmed events"));
    assert.ok(w.includes("News breadth expansion is a planning recommendation, not a runtime change"));
    assert.ok(w.includes("Freeze is a reviewer worklist only, not gold"));
    assert.ok(w.includes("Reviewer first contact is manual; the system never sends labels or messages"));
    assert.ok(w.includes("Hot Post preview is internal-only and cannot be published before R1/R2 gates"));
  });

  it("(ADR#92) keeps the date-pinned frontier sanitized with the 10 ADR#92 fields (no forbidden keys)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_DATE_PINNED_FRONTIER));
    for (const k of [
      "live_attempt_pack_status", "live_attempt_pack_next_action", "news_breadth_trigger_status",
      "recommended_provider_expansion", "freeze_package_hardening_status", "freeze_artifact_safe",
      "r1_first_contact_protocol_status", "r1_first_contact_next_action", "hot_post_preview_status",
      "hot_post_preview_public_blocked",
    ]) {
      assert.ok(k in SAMPLE_DATE_PINNED_FRONTIER, `missing ${k}`);
    }
  });

  it("(ADR#93) shows promotion draft-ready + command pack template-only + freeze→R1 blocked + activation/feedback runtime disabled + provider expansion not triggered", () => {
    const byLabel = Object.fromEntries(
      toR1DatePinnedLiveRunFrontierDisplayRows(SAMPLE_DATE_PINNED_FRONTIER).map((r) => [r.label, r.value]),
    );
    // payload 미제공 → promotion 은 draft(operator 확인 대기), command pack 은 event 미주입 template-only(명령 ready=참).
    assert.equal(byLabel["Real payload promotion status (draft-only)"], "promotion_draft_ready_operator_must_confirm");
    assert.equal(byLabel["Operator live command pack status"], "command_pack_ready_no_event_template_only");
    assert.equal(byLabel["Validate-only command ready (no network)"], "true");
    assert.equal(byLabel["Live-run command ready (requires approval)"], "true");
    assert.equal(byLabel["Expected provider calls"], "3");
    assert.equal(byLabel["Real payload present"], "false");
    // freeze 0 → freeze→R1 blocked·label 명령 ready 는 FR1_READY 게이트로 false(status 와 정합). activation/feedback runtime 0.
    assert.equal(byLabel["Freeze→R1 executable checklist status"], "blocked_no_production_candidate_freeze");
    assert.equal(byLabel["Label intake command ready"], "false");
    assert.equal(byLabel["Hot Post activation map status (runtime disabled)"], "hot_post_activation_map_defined_runtime_disabled");
    assert.equal(byLabel["Community feedback loop status (runtime disabled)"], "community_feedback_loop_defined_runtime_disabled");
    assert.equal(byLabel["Next provider expansion status (planning only)"], "no_expansion_recommended");
  });

  it("(ADR#93) warns: packs need manual verify + validate/dry-run no live + live run needs approval + labels need agreement + feedback loop is future-only", () => {
    const w = r1DatePinnedLiveRunFrontierWarnings(SAMPLE_DATE_PINNED_FRONTIER);
    assert.ok(w.includes("Live attempt packs must be manually verified before becoming real payloads"));
    assert.ok(w.includes("Validate-only and dry-run do not call live providers"));
    assert.ok(w.includes("Live run requires operator-confirmed payload and live_approved=true"));
    assert.ok(w.includes("Returned labels require validation and agreement before R1 gold"));
    assert.ok(w.includes("Community feedback loop is future contract only; comment runtime is disabled"));
  });

  it("(ADR#93) keeps the date-pinned frontier sanitized with the 16 ADR#93 fields (no forbidden keys)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_DATE_PINNED_FRONTIER));
    for (const k of [
      "real_payload_promotion_status", "real_payload_promotion_next_action", "operator_live_command_pack_status",
      "validate_payload_command_ready", "dry_run_command_ready", "live_run_command_ready", "expected_provider_calls",
      "real_payload_present", "real_payload_valid", "freeze_to_r1_status", "label_validation_command_ready",
      "label_intake_command_ready", "agreement_check_command_ready", "hot_post_activation_map_status",
      "community_feedback_loop_status", "next_provider_expansion_status",
    ]) {
      assert.ok(k in SAMPLE_DATE_PINNED_FRONTIER, `missing ${k}`);
    }
  });

  it("(ADR#94) keeps the date-pinned frontier sanitized with the 7 ADR#94 fields (no forbidden keys)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_DATE_PINNED_FRONTIER));
    for (const k of [
      "first_real_payload_sprint_status", "operator_confirmed_ready_package_status", "unified_live_closure_status",
      "freeze_r1_dry_run_status", "ai_replies_guard_audit_status", "public_runtime_kill_switch_status",
      "source_graph_timeseries_contract_status",
    ]) {
      assert.ok(k in SAMPLE_DATE_PINNED_FRONTIER, `missing ${k}`);
    }
  });

  it("(ADR#95) keeps the date-pinned frontier sanitized with the 7 ADR#95 fields (no forbidden keys)", () => {
    assert.doesNotThrow(() => assertOpsContractSafe(SAMPLE_DATE_PINNED_FRONTIER));
    for (const k of [
      "evidence_payload_kit_status", "operator_verification_worksheet_status", "payload_template_hardening_status",
      "first_payload_evidence_binder_status", "reviewer_packet_dry_run_status", "ai_replies_gate_design_status",
      "source_graph_hot_post_integration_status",
    ]) {
      assert.ok(k in SAMPLE_DATE_PINNED_FRONTIER, `missing ${k}`);
    }
  });
});
