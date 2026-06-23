import { api, ApiError } from "@/lib/api/client";
import type { Event } from "@/lib/api/types";
import EventTimelineList from "@/components/EventTimelineList";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";

export const metadata = { title: "사건 타임라인 | Event Intelligence" };

export default async function EventTimelinePage() {
  let events: Event[] = [];
  let error: string | null = null;
  let disabled = false;

  try {
    events = await api.listEventTimeline();
  } catch (e) {
    // flag off → 404. 사용자에겐 "아직 비활성" 빈 상태로(에러 아님).
    if (e instanceof ApiError && e.status === 404) {
      disabled = true;
    } else {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">사건 타임라인</h1>
      <p className="text-sm text-gray-500">
        같은 사건은 하나의 타임라인으로 누적됩니다 — 새 보도는 새 카드가 아니라
        업데이트로 붙습니다.
      </p>
      {error ? (
        <ErrorState title="타임라인 로드 실패" message={error} />
      ) : disabled ? (
        <EmptyState message="사건 타임라인이 아직 활성화되지 않았습니다." />
      ) : (
        <>
          <p className="text-sm text-gray-500">{events.length}건</p>
          <EventTimelineList events={events} />
        </>
      )}
    </div>
  );
}
