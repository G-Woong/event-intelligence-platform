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
