import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Event Intelligence",
  description: "실시간 글로벌 사건·이벤트 인텔리전스",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-gray-950 text-gray-100">
        <nav className="border-b border-gray-800 bg-gray-900">
          <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-6">
            <Link href="/" className="text-lg font-bold text-white hover:text-blue-400 transition-colors">
              EI
            </Link>
            <Link href="/events" className="text-sm text-gray-300 hover:text-white transition-colors">
              이벤트
            </Link>
            <Link href="/search" className="text-sm text-gray-300 hover:text-white transition-colors">
              검색
            </Link>
            <Link href="/themes" className="text-sm text-gray-300 hover:text-white transition-colors">
              테마
            </Link>
            <Link href="/sectors" className="text-sm text-gray-300 hover:text-white transition-colors">
              섹터
            </Link>
            <Link href="/admin" className="ml-auto text-sm text-gray-400 hover:text-white transition-colors">
              관리
            </Link>
          </div>
        </nav>
        <main className="mx-auto max-w-6xl px-4 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
