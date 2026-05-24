import Link from "next/link";
import { api } from "@/lib/api/client";
import type { Sector } from "@/lib/api/types";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";

export const metadata = { title: "섹터 | Event Intelligence" };

export default async function SectorsPage() {
  let sectors: Sector[] = [];
  let error: string | null = null;

  try {
    sectors = await api.listSectors();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">섹터 목록</h1>
      {error ? (
        <ErrorState title="섹터 로드 실패" message={error} />
      ) : sectors.length === 0 ? (
        <EmptyState message="등록된 섹터가 없습니다." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sectors.map((s) => (
            <Link
              key={s.id}
              href={`/sectors/${s.id}`}
              className="rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-600 transition-colors"
            >
              <h3 className="mb-1 font-semibold text-white">{s.name}</h3>
              {s.description && (
                <p className="text-sm text-gray-400 line-clamp-2">{s.description}</p>
              )}
              {s.event_count !== undefined && (
                <p className="mt-2 text-xs text-gray-600">{s.event_count}건</p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
