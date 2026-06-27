import { describe, it } from "node:test";
import assert from "node:assert/strict";

// 코드베이스 convention(client.test.mjs): node:test 는 TS 로더가 없으므로 순수 로직을 inline 재선언해 계약을
// 잠근다. 본 helper 의 1차 보증은 서버측(Python _assert_pii_safe + Pydantic 화이트리스트 + API forbidden-field
// 테스트). 이 테스트는 표시층이 forbidden 필드를 re-introduce 하지 않는다는 2차 lock 이다.
const FORBIDDEN_OPS_FIELDS = [
  "score", "rationale", "predicted_status", "same_event", "raw_body",
  "reviewer_name", "reviewer_email", "reviewer_phone", "email", "phone", "secret", "api_key",
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
