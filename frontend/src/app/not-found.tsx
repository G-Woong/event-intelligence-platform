import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <h2 className="text-4xl font-bold text-gray-500">404</h2>
      <p className="text-gray-400">페이지를 찾을 수 없습니다.</p>
      <Link
        href="/"
        className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 transition-colors"
      >
        홈으로
      </Link>
    </div>
  );
}
