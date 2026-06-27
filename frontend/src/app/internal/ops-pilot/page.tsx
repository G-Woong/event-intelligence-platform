// ADR#72 — internal ops dashboard seed(reviewer pilot execution workflow state·read-only·public truth 아님).
//
// 안전 게이트: ① server-only env `INTERNAL_OPS_DASHBOARD_ENABLED`(NEXT_PUBLIC 아님 → 클라이언트 미전송) 미설정 시
// notFound()(404). ② 데이터는 server-side adminFetch(X-Admin-Token)로 backend admin-gated 엔드포인트에서만.
// nav(layout.tsx)에 링크 없음(public 미노출). same_event truth/score/rationale/predicted_status/raw PII 미표시.
import { notFound } from "next/navigation";

import { adminFetch } from "@/lib/api/server";
import type { InternalOpsPilotExecutionStatus } from "@/lib/api/types";
import {
  OPS_NO_GO_COPY,
  assertOpsContractSafe,
  toOpsDisplayRows,
} from "@/lib/ops/opsPilotExecutionView";

export const dynamic = "force-dynamic";
export const metadata = { title: "Internal Ops · Pilot Execution" };

export default async function InternalOpsPilotExecutionPage() {
  // server-only env gate(기본 미설정 → 404). public 배포에서 reachable 하지 않게 opt-in.
  if (process.env.INTERNAL_OPS_DASHBOARD_ENABLED !== "true") {
    notFound();
  }

  let status: InternalOpsPilotExecutionStatus | null = null;
  let error: string | null = null;
  try {
    status = await adminFetch<InternalOpsPilotExecutionStatus>(
      "/api/internal/ops/pilot-execution",
    );
    assertOpsContractSafe(status); // 심층 방어: forbidden 필드 발견 시 렌더 차단.
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  const banners = [
    OPS_NO_GO_COPY.notPublicTruth,
    OPS_NO_GO_COPY.noMerge,
    OPS_NO_GO_COPY.goldUnverified,
    OPS_NO_GO_COPY.requiresMergeGate,
  ];

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold text-white">{OPS_NO_GO_COPY.heading}</h1>
        <div className="flex flex-wrap gap-2 text-xs">
          {banners.map((c) => (
            <span
              key={c}
              className="rounded border border-amber-700 bg-amber-950 px-2 py-1 text-amber-300"
            >
              {c}
            </span>
          ))}
        </div>
        <p className="text-sm text-gray-400">
          Internal operations view of the reviewer pilot pipeline. Workflow state only — not a public
          Intelligence Unit, not a verified same-event truth, and no merge is performed here.
        </p>
      </header>

      {error ? (
        <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-300">
          {OPS_NO_GO_COPY.awaitingReturn} — backend status unavailable ({error}).
        </div>
      ) : status ? (
        <>
          <table className="w-full text-sm">
            <tbody>
              {toOpsDisplayRows(status).map((row) => (
                <tr key={row.label} className="border-b border-gray-800">
                  <td className="py-2 pr-4 text-gray-400">{row.label}</td>
                  <td className="py-2 font-mono text-gray-100">{row.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex flex-wrap gap-2 text-xs text-gray-500">
            {Object.entries(status.flags).map(([k, v]) => (
              <span key={k} className="rounded bg-gray-800 px-2 py-1">
                {k}={String(v)}
              </span>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
