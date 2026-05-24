import { api } from "@/lib/api/client";
import type { FinalEventCard } from "@/lib/api/types";
import EventList from "@/components/EventList";
import ErrorState from "@/components/ErrorState";

export const metadata = { title: "이벤트 목록 | Event Intelligence" };

export default async function EventsPage() {
  let events: FinalEventCard[] = [];
  let error: string | null = null;

  try {
    events = await api.listEvents();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">이벤트 목록</h1>
      {error ? (
        <ErrorState title="이벤트 로드 실패" message={error} />
      ) : (
        <>
          <p className="text-sm text-gray-500">{events.length}건</p>
          <EventList events={events} />
        </>
      )}
    </div>
  );
}
