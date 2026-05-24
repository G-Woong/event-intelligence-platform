import Link from "next/link";
import type { FinalEventCard } from "@/lib/api/types";

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 70
      ? "bg-green-900/60 text-green-300"
      : pct >= 40
        ? "bg-yellow-900/60 text-yellow-300"
        : "bg-red-900/60 text-red-300";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}

export default function EventCard({ event }: { event: FinalEventCard }) {
  return (
    <Link
      href={`/events/${event.id}`}
      className="block rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-600 transition-colors"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-white leading-snug">
          {event.title}
        </h3>
        <ConfidenceBadge score={event.confidence_score} />
      </div>
      <p className="mb-3 text-xs text-gray-400 line-clamp-2">{event.summary}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-blue-900/50 px-2 py-0.5 text-xs text-blue-300">
          {event.theme}
        </span>
        {event.sectors.slice(0, 2).map((s) => (
          <span
            key={s}
            className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400"
          >
            {s}
          </span>
        ))}
        <span className="ml-auto text-xs text-gray-600">
          {new Date(event.created_at).toLocaleDateString("ko-KR")}
        </span>
      </div>
    </Link>
  );
}
