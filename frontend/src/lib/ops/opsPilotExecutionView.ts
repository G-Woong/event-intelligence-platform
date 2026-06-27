// ADR#72 — internal ops dashboard 표시용 순수 view/sanitize helper(public truth 아님·read-only).
//
// backend 가 sanitized `InternalOpsPilotExecutionStatus` 만 내려주지만, UI 가 실수로 forbidden 필드를
// re-introduce 하지 못하게 한 겹 더 막는다(R-OpsUIPrematureTruth·심층 방어). same_event truth·semantic score·
// model rationale·predicted_status·reviewer raw PII 는 표시 대상이 아니다 — 발견 시 fail-loud.
import type { InternalOpsPilotExecutionStatus } from "@/lib/api/types";

// internal ops dashboard 가 절대 표시하면 안 되는 키(있으면 오염). recursive 검사.
export const FORBIDDEN_OPS_FIELDS: readonly string[] = [
  "score",
  "rationale",
  "predicted_status",
  "same_event",
  "raw_body",
  "reviewer_name",
  "reviewer_email",
  "reviewer_phone",
  "email",
  "phone",
  "secret",
  "api_key",
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
