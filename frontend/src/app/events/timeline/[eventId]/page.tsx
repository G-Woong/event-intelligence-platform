import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api/client";
import type { EventTimelineResponse } from "@/lib/api/types";
import EventUpdateItem from "@/components/EventUpdateItem";
import ErrorState from "@/components/ErrorState";

export const metadata = { title: "사건 타임라인 상세 | Event Intelligence" };

const STATUS_LABEL: Record<string, string> = {
  active: "활성",
  dormant: "휴면",
  closed: "종료",
};

export default async function EventTimelineDetailPage({
  params,
}: {
  params: Promise<{ eventId: string }>;
}) {
  const { eventId } = await params;

  let data: EventTimelineResponse;
  try {
    data = await api.getEventTimeline(eventId);
  } catch (e) {
    // flag off / 미매핑(held degenerate) / 없는 event → 404 → notFound.
    if (e instanceof ApiError && e.status === 404) notFound();
    // 그 외(backend 장애/네트워크)는 raw 메시지 노출 없이 일반 안내(R-EventTimelineRenderHardening).
    return (
      <ErrorState
        title="타임라인 로드 실패"
        message="타임라인을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."
      />
    );
  }

  const { event, updates } = data;
  // domains·tags 는 독립 free-form list — 교집합 가능. dedup 해 중복 칩/중복 React key 방지.
  const labels = [...new Set([...event.domains, ...event.tags])];

  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <header>
        <div className="mb-2 flex items-center gap-3">
          <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300">
            {STATUS_LABEL[event.status] ?? event.status}
          </span>
          <span className="text-xs text-gray-600">
            첫 관측 {new Date(event.first_seen_at).toLocaleDateString("ko-KR")} · 최근
            업데이트 {new Date(event.last_update_at).toLocaleDateString("ko-KR")}
          </span>
        </div>
        <h1 className="text-2xl font-bold text-white">{event.canonical_title}</h1>
        {labels.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {labels.map((l) => (
              <span
                key={l}
                className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400"
              >
                {l}
              </span>
            ))}
          </div>
        )}
      </header>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          타임라인 ({updates.length})
        </h2>
        {updates.length === 0 ? (
          <p className="text-sm text-gray-500">아직 업데이트가 없습니다.</p>
        ) : (
          <ol className="mt-1">
            {updates.map((u) => (
              <EventUpdateItem key={u.id} update={u} />
            ))}
          </ol>
        )}
      </section>
    </article>
  );
}
