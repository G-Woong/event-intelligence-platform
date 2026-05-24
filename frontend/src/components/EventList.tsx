import type { FinalEventCard } from "@/lib/api/types";
import EventCard from "./EventCard";
import EmptyState from "./EmptyState";

export default function EventList({ events }: { events: FinalEventCard[] }) {
  if (events.length === 0) {
    return <EmptyState message="이벤트가 없습니다. 수집기가 실행되면 자동으로 표시됩니다." />;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {events.map((e) => (
        <EventCard key={e.id} event={e} />
      ))}
    </div>
  );
}
