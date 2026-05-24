import Link from "next/link";
import { api } from "@/lib/api/client";
import EventList from "@/components/EventList";
import ErrorState from "@/components/ErrorState";

export default async function Home() {
  let recentEvents: import("@/lib/api/types").FinalEventCard[] = [];
  let error: string | null = null;

  try {
    const all = await api.listEvents();
    recentEvents = all.slice(0, 6);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="mb-2 text-3xl font-bold text-white">
          Event Intelligence
        </h1>
        <p className="text-gray-400">
          전세계 실시간 사건·이벤트를 수집·분석·랭킹합니다.
        </p>
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">최근 이벤트</h2>
          <Link
            href="/events"
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            전체 보기 →
          </Link>
        </div>
        {error ? (
          <ErrorState title="이벤트 로드 실패" message={error} />
        ) : (
          <EventList events={recentEvents} />
        )}
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        <Link
          href="/search"
          className="rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-600 transition-colors"
        >
          <h3 className="mb-1 font-semibold text-white">검색</h3>
          <p className="text-sm text-gray-400">키워드로 이벤트 검색</p>
        </Link>
        <Link
          href="/themes"
          className="rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-600 transition-colors"
        >
          <h3 className="mb-1 font-semibold text-white">테마별 탐색</h3>
          <p className="text-sm text-gray-400">지정학, 경제, 기술 등</p>
        </Link>
        <Link
          href="/sectors"
          className="rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-600 transition-colors"
        >
          <h3 className="mb-1 font-semibold text-white">섹터별 탐색</h3>
          <p className="text-sm text-gray-400">에너지, 금융, 방산 등</p>
        </Link>
      </section>
    </div>
  );
}
