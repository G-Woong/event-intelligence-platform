import type { Event } from "@/lib/api/types";
import EventTimelineCard from "./EventTimelineCard";
import EmptyState from "./EmptyState";

export default function EventTimelineList({ events }: { events: Event[] }) {
  if (events.length === 0) {
    return (
      <EmptyState message="추적 중인 사건 타임라인이 없습니다. 수집·결선기가 실행되면 자동으로 표시됩니다." />
    );
  }
  return (
    <div className="space-y-3">
      {events.map((e) => (
        <EventTimelineCard key={e.id} event={e} />
      ))}
    </div>
  );
}
