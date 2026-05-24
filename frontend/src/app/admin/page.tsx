import { adminFetch } from "@/lib/api/server";
import HealthStatus from "@/components/HealthStatus";
import AdminPanel from "@/components/AdminPanel";
import ErrorState from "@/components/ErrorState";
import type { HealthResponse } from "@/lib/api/types";

export const metadata = { title: "관리자 | Event Intelligence" };

export default async function AdminPage() {
  let health: HealthResponse | null = null;
  let healthError: string | null = null;

  try {
    health = await adminFetch<HealthResponse>("/health");
  } catch (e) {
    healthError = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-white">관리자</h1>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-300">시스템 상태</h2>
        {healthError ? (
          <ErrorState title="상태 조회 실패" message={healthError} />
        ) : health ? (
          <HealthStatus health={health} />
        ) : null}
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-300">작업</h2>
        <AdminPanel />
      </section>
    </div>
  );
}
