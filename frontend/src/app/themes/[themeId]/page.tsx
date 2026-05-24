import { api } from "@/lib/api/client";
import type { FinalEventCard } from "@/lib/api/types";
import EventList from "@/components/EventList";
import ErrorState from "@/components/ErrorState";

export const metadata = { title: "테마별 이벤트 | Event Intelligence" };

export default async function ThemeDetailPage({
  params,
}: {
  params: Promise<{ themeId: string }>;
}) {
  const { themeId } = await params;

  let events: FinalEventCard[] = [];
  let error: string | null = null;

  try {
    events = await api.themeEvents(themeId);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="mb-1 text-sm text-gray-500">테마</p>
        <h1 className="text-2xl font-bold text-white">{themeId}</h1>
      </div>
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
