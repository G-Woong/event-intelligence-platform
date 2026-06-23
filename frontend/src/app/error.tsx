"use client";

// Next.js 는 error/reset prop 을 전달하지만, raw 에러는 의도적으로 렌더하지 않으므로
// reset 만 사용한다(스택/내부 경로/DB 힌트 노출 차단 — 일반 안내만 표시).
export default function Error({ reset }: { reset: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <h2 className="text-xl font-semibold text-red-400">오류가 발생했습니다</h2>
      {/* raw 에러 메시지(스택/내부 경로/DB 힌트)를 노출하지 않는다 — 일반 안내만. */}
      <p className="text-sm text-gray-400">
        문제가 발생했습니다. 잠시 후 다시 시도해 주세요.
      </p>
      <button
        onClick={reset}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 transition-colors"
      >
        다시 시도
      </button>
    </div>
  );
}
