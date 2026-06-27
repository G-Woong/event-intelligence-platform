// ADR#72 — internal ops dashboard 표시용 순수 view/sanitize helper(public truth 아님·read-only).
//
// backend 가 sanitized `InternalOpsPilotExecutionStatus` 만 내려주지만, UI 가 실수로 forbidden 필드를
// re-introduce 하지 못하게 한 겹 더 막는다(R-OpsUIPrematureTruth·심층 방어). same_event truth·semantic score·
// model rationale·predicted_status·reviewer raw PII 는 표시 대상이 아니다 — 발견 시 fail-loud.
import type {
  InternalOpsPilotExecutionStatus,
  InternalOpsPreflightStatus,
  InternalOpsR1AcquisitionStatus,
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
