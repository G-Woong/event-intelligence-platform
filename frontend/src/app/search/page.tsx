import { api, ApiError } from "@/lib/api/client";
import SearchBar from "@/components/SearchBar";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";
import EventCard from "@/components/EventCard";
import type { FinalEventCard } from "@/lib/api/types";

export const metadata = { title: "검색 | Event Intelligence" };

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;

  let hits: FinalEventCard[] = [];
  let total = 0;
  let error: string | null = null;
  let searchUnavailable = false;

  if (q) {
    try {
      const result = await api.search(q);
      hits = result.hits as unknown as FinalEventCard[];
      total = result.total;
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        searchUnavailable = true;
      } else {
        error = e instanceof Error ? e.message : String(e);
      }
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">이벤트 검색</h1>
      <SearchBar defaultValue={q ?? ""} />

      {searchUnavailable && (
        <ErrorState
          title="검색 서비스 일시 중단"
          message="OpenSearch가 응답하지 않습니다. 잠시 후 다시 시도해 주세요."
        />
      )}
      {error && <ErrorState title="검색 오류" message={error} />}

      {q && !searchUnavailable && !error && (
        <>
          <p className="text-sm text-gray-500">
            &quot;{q}&quot; 검색 결과 {total}건
          </p>
          {hits.length === 0 ? (
            <EmptyState message="검색 결과가 없습니다." />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {hits.map((h) => (
                <EventCard key={h.id} event={h} />
              ))}
            </div>
          )}
        </>
      )}

      {!q && !searchUnavailable && !error && (
        <EmptyState message="검색어를 입력하세요." />
      )}
    </div>
  );
}
