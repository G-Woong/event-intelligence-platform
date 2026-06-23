import Link from "next/link";
import type { Event } from "@/lib/api/types";

const STATUS_LABEL: Record<string, string> = {
  active: "활성",
  dormant: "휴면",
  closed: "종료",
};

const STATUS_COLOR: Record<string, string> = {
  active: "bg-green-900/60 text-green-300",
  dormant: "bg-gray-800 text-gray-400",
  closed: "bg-gray-800 text-gray-500",
};

export default function EventTimelineCard({ event }: { event: Event }) {
  // domains·tags 는 독립 free-form list — 교집합 가능. dedup 해 중복 칩/중복 React key 방지.
  const labels = [...new Set([...event.domains, ...event.tags])].slice(0, 4);
  return (
    <Link
      href={`/events/timeline/${event.id}`}
      className="block rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-600 transition-colors"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-white leading-snug">
          {event.canonical_title}
        </h3>
        <span
          className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
            STATUS_COLOR[event.status] ?? "bg-gray-800 text-gray-400"
          }`}
        >
          {STATUS_LABEL[event.status] ?? event.status}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {labels.map((l) => (
          <span
            key={l}
            className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400"
          >
            {l}
          </span>
        ))}
        <span className="ml-auto text-xs text-gray-600">
          업데이트 {new Date(event.last_update_at).toLocaleDateString("ko-KR")}
        </span>
      </div>
    </Link>
  );
}
