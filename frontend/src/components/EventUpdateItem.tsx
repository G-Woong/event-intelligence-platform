import type { EventUpdate, EventUpdateEvidence } from "@/lib/api/types";

// 출처 링크는 http/https 만 허용(javascript: 등 스킴 주입 차단). 그 외엔 링크화하지 않음.
export function isSafeHttpUrl(u: string | undefined): u is string {
  return !!u && (u.startsWith("http://") || u.startsWith("https://"));
}

function EvidenceRow({ ev }: { ev: EventUpdateEvidence }) {
  const meta = [ev.source_type, ev.role, ev.relation].filter(Boolean).join(" · ");
  return (
    <li className="text-xs text-gray-400">
      {isSafeHttpUrl(ev.url) ? (
        <a
          href={ev.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="text-blue-400 hover:text-blue-300 break-all"
        >
          {ev.url}
        </a>
      ) : (
        <span className="text-gray-500">{ev.source_type ?? "출처"}</span>
      )}
      {meta && <span className="ml-2 text-gray-600">({meta})</span>}
    </li>
  );
}

export default function EventUpdateItem({ update }: { update: EventUpdate }) {
  return (
    <li className="relative border-l border-gray-800 pl-5 pb-5">
      <span className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full bg-blue-500" />
      <time className="text-xs text-gray-500">
        {new Date(update.observed_at).toLocaleString("ko-KR")}
      </time>
      <p className="mt-1 text-sm text-gray-200 leading-relaxed">
        {update.delta_summary}
      </p>
      {update.evidence.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {update.evidence.map((ev, i) => (
            <EvidenceRow key={i} ev={ev} />
          ))}
        </ul>
      )}
      {update.added_domains.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {update.added_domains.map((d) => (
            <span
              key={d}
              className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400"
            >
              +{d}
            </span>
          ))}
        </div>
      )}
    </li>
  );
}
