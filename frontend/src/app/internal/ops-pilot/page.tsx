// ADR#72/#73 — internal ops dashboard seed(reviewer pilot workflow state + auth/deploy preflight·read-only·public truth 아님).
//
// 안전 게이트: ① server-only env `INTERNAL_OPS_DASHBOARD_ENABLED`(NEXT_PUBLIC 아님 → 클라이언트 미전송) 미설정 시
// notFound()(404). ② 데이터는 server-side adminFetch(X-Admin-Token)로 backend admin-gated 엔드포인트에서만.
// nav(layout.tsx)에 링크 없음(public 미노출). same_event truth/score/rationale/predicted_status/raw PII 미표시.
// admin token **값**은 표시하지 않는다(preflight 의 admin_token_configured 존재 여부만).
import { notFound } from "next/navigation";

import { adminFetch } from "@/lib/api/server";
import type {
  InternalOpsPilotExecutionStatus,
  InternalOpsPreflightStatus,
  InternalOpsR1AcquisitionStatus,
  InternalOpsR1PilotBatchStatus,
} from "@/lib/api/types";
import {
  OPS_NO_GO_COPY,
  OPS_R1_BATCH_COPY,
  OPS_R1_COPY,
  assertOpsContractSafe,
  preflightWarnings,
  r1BatchWarnings,
  r1Warnings,
  toOpsDisplayRows,
  toPreflightDisplayRows,
  toR1BatchDisplayRows,
  toR1DisplayRows,
} from "@/lib/ops/opsPilotExecutionView";

export const dynamic = "force-dynamic";
export const metadata = { title: "Internal Ops · Pilot Execution" };

async function fetchSafe<T>(path: string): Promise<{ data: T | null; error: string | null }> {
  try {
    const data = await adminFetch<T>(path);
    assertOpsContractSafe(data); // 심층 방어: forbidden 필드 발견 시 throw → null.
    return { data, error: null };
  } catch (e) {
    return { data: null, error: e instanceof Error ? e.message : String(e) };
  }
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">{title}</h2>
      {children}
    </section>
  );
}

function RowTable({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map((row) => (
          <tr key={row.label} className="border-b border-gray-800">
            <td className="py-2 pr-4 text-gray-400">{row.label}</td>
            <td className="py-2 font-mono text-gray-100">{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function InternalOpsPilotExecutionPage() {
  // server-only env gate(기본 미설정 → 404). public 배포에서 reachable 하지 않게 opt-in.
  if (process.env.INTERNAL_OPS_DASHBOARD_ENABLED !== "true") {
    notFound();
  }

  const { data: status, error: statusError } =
    await fetchSafe<InternalOpsPilotExecutionStatus>("/api/internal/ops/pilot-execution");
  const { data: preflight, error: preflightError } =
    await fetchSafe<InternalOpsPreflightStatus>("/api/internal/ops/preflight");
  const { data: r1, error: r1Error } =
    await fetchSafe<InternalOpsR1AcquisitionStatus>("/api/internal/ops/r1-gold-acquisition");
  const { data: r1Batch, error: r1BatchError } =
    await fetchSafe<InternalOpsR1PilotBatchStatus>("/api/internal/ops/r1-pilot-batch");

  const banners = [
    OPS_NO_GO_COPY.notPublicTruth,
    OPS_NO_GO_COPY.noMerge,
    OPS_NO_GO_COPY.goldUnverified,
    OPS_NO_GO_COPY.requiresMergeGate,
    OPS_R1_COPY.internalOnly,
  ];
  // dedupe — 여러 패널이 같은 No-Go 문구를 낼 수 있어 React key 충돌 방지(예: "R2~R7 remain No-Go").
  const warnings = [
    ...new Set([
      ...(preflight ? preflightWarnings(preflight) : []),
      ...(r1 ? r1Warnings(r1) : []),
      ...(r1Batch ? r1BatchWarnings(r1Batch) : []),
    ]),
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

      {warnings.length > 0 ? (
        <div className="flex flex-wrap gap-2 text-xs">
          {warnings.map((w) => (
            <span
              key={w}
              className="rounded border border-rose-700 bg-rose-950 px-2 py-1 text-rose-300"
            >
              {w}
            </span>
          ))}
        </div>
      ) : null}

      {preflight ? (
        <Section title="Auth / deployment posture">
          <RowTable rows={toPreflightDisplayRows(preflight)} />
        </Section>
      ) : (
        <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-300">
          Preflight unavailable ({preflightError}).
        </div>
      )}

      {status ? (
        <Section title="Reviewer pilot workflow">
          <RowTable rows={toOpsDisplayRows(status)} />
          <div className="flex flex-wrap gap-2 text-xs text-gray-500">
            {Object.entries(status.flags).map(([k, v]) => (
              <span key={k} className="rounded bg-gray-800 px-2 py-1">
                {k}={String(v)}
              </span>
            ))}
          </div>
        </Section>
      ) : (
        <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-300">
          {OPS_NO_GO_COPY.awaitingReturn} — backend status unavailable ({statusError}).
        </div>
      )}

      {r1 ? (
        <Section title="R1 gold acquisition (production gold floor · gap)">
          <p className="text-xs text-gray-500">
            {OPS_R1_COPY.blockedByLabels}. {OPS_R1_COPY.goldZeroUntilImport}. {OPS_R1_COPY.laddersNoGo}. The
            target floor is an operating floor, not a verified production truth — R1 is satisfied only when
            calibration is ready. Synthetic / test / model labels never count as production gold.
          </p>
          <RowTable rows={toR1DisplayRows(r1)} />
          {r1.next_manual_actions.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-gray-300">
              {r1.next_manual_actions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          ) : null}
        </Section>
      ) : (
        <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-300">
          R1 gold acquisition status unavailable ({r1Error}).
        </div>
      )}

      {r1Batch ? (
        <Section title="R1 reviewer pilot batch (freeze · launch readiness)">
          <p className="text-xs text-gray-500">
            {OPS_R1_BATCH_COPY.worklistNotTruth}. {OPS_R1_BATCH_COPY.manualLaunchRequired}.{" "}
            {OPS_R1_BATCH_COPY.goldZeroUntilImport}. {OPS_R1_BATCH_COPY.laddersNoGo}. The frozen batch is built
            from a synthetic fixture (structural readiness only) — real production gold requires acquiring real
            candidate pairs from live source overlap and real reviewer labels. The batch does not increase
            production gold and does not assert same-event truth.
          </p>
          <RowTable rows={toR1BatchDisplayRows(r1Batch)} />
          <p className="text-sm text-gray-300">
            <span className="text-gray-500">Next manual action:</span> {r1Batch.next_manual_action}
          </p>
          <p className="font-mono text-xs text-gray-500">{r1Batch.validation_command}</p>
        </Section>
      ) : (
        <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-300">
          R1 pilot batch status unavailable ({r1BatchError}).
        </div>
      )}

      {preflight && preflight.r1_r7_stages.length > 0 ? (
        <Section title="RAG/KG/Entity readiness (R1–R7 · gated)">
          <p className="text-xs text-gray-500">
            Each stage is gated: public Intelligence Unit stays No-Go until the production gold floor (R1)
            and MERGE_GATE (R2) pass. Community = reaction, market = signal, catalog = enrichment — never an anchor.
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-left text-gray-500">
                <th className="py-1 pr-3">Stage</th>
                <th className="py-1 pr-3">Goal</th>
                <th className="py-1 pr-3">Status</th>
                <th className="py-1 pr-3">Blocker</th>
                <th className="py-1">Next action</th>
              </tr>
            </thead>
            <tbody>
              {preflight.r1_r7_stages.map((s) => (
                <tr key={s.stage} className="border-b border-gray-800 align-top">
                  <td className="py-2 pr-3 font-mono text-gray-200">{s.stage}</td>
                  <td className="py-2 pr-3 text-gray-300">{s.goal}</td>
                  <td className="py-2 pr-3 font-mono text-amber-300">{s.current_status}</td>
                  <td className="py-2 pr-3 text-gray-400">{s.blocker}</td>
                  <td className="py-2 text-gray-400">{s.next_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {preflight && preflight.next_actions.length > 0 ? (
        <Section title="Operator next actions">
          <ul className="list-disc space-y-1 pl-5 text-sm text-gray-300">
            {preflight.next_actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}
