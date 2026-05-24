import Link from "next/link";
import { api } from "@/lib/api/client";
import type { Theme } from "@/lib/api/types";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";

export const metadata = { title: "테마 | Event Intelligence" };

export default async function ThemesPage() {
  let themes: Theme[] = [];
  let error: string | null = null;

  try {
    themes = await api.listThemes();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">테마 목록</h1>
      {error ? (
        <ErrorState title="테마 로드 실패" message={error} />
      ) : themes.length === 0 ? (
        <EmptyState message="등록된 테마가 없습니다." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {themes.map((t) => (
            <Link
              key={t.id}
              href={`/themes/${t.id}`}
              className="rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-600 transition-colors"
            >
              <h3 className="mb-1 font-semibold text-white">{t.name}</h3>
              {t.description && (
                <p className="text-sm text-gray-400 line-clamp-2">{t.description}</p>
              )}
              {t.event_count !== undefined && (
                <p className="mt-2 text-xs text-gray-600">{t.event_count}건</p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
