"use client";

import { useRouter, useSearchParams } from "next/navigation";

interface Props {
  themes: string[];
  sectors: string[];
  currentTheme?: string;
  currentSector?: string;
}

export default function EventFilters({
  themes,
  sectors,
  currentTheme,
  currentSector,
}: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function navigate(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    router.push(`/events?${params.toString()}`);
  }

  return (
    <div className="flex flex-wrap gap-3">
      <select
        value={currentTheme ?? ""}
        onChange={(e) => navigate("theme", e.target.value)}
        className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
      >
        <option value="">모든 테마</option>
        {themes.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      <select
        value={currentSector ?? ""}
        onChange={(e) => navigate("sector", e.target.value)}
        className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
      >
        <option value="">모든 섹터</option>
        {sectors.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </div>
  );
}
