import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api/client";

export const metadata = { title: "이벤트 상세 | Event Intelligence" };

export default async function EventDetailPage({
  params,
}: {
  params: Promise<{ eventId: string }>;
}) {
  const { eventId } = await params;

  let event;
  try {
    event = await api.getEvent(eventId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const confidencePct = Math.round(event.confidence_score * 100);

  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <header>
        <div className="mb-2 flex items-start gap-3">
          <span className="rounded bg-blue-900/50 px-2 py-0.5 text-xs text-blue-300">
            {event.theme}
          </span>
          <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
            신뢰도 {confidencePct}%
          </span>
          <span className="ml-auto text-xs text-gray-600">
            {new Date(event.created_at).toLocaleString("ko-KR")}
          </span>
        </div>
        <h1 className="text-2xl font-bold text-white">{event.title}</h1>
      </header>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
          요약
        </h2>
        <p className="text-gray-300 leading-relaxed">{event.summary}</p>
      </section>

      {event.impact_path && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            영향 경로
          </h2>
          <p className="text-gray-300 leading-relaxed">{event.impact_path}</p>
        </section>
      )}

      {event.evidence.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            근거
          </h2>
          <ul className="space-y-1">
            {event.evidence.map((e, i) => (
              <li key={i} className="text-sm text-gray-400 before:content-['·_']">
                {e}
              </li>
            ))}
          </ul>
        </section>
      )}

      {event.entities.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            관련 엔티티
          </h2>
          <div className="flex flex-wrap gap-2">
            {event.entities.map((en) => (
              <span
                key={en}
                className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300"
              >
                {en}
              </span>
            ))}
          </div>
        </section>
      )}

      {event.sectors.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            섹터
          </h2>
          <div className="flex flex-wrap gap-2">
            {event.sectors.map((s) => (
              <span
                key={s}
                className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400"
              >
                {s}
              </span>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}
