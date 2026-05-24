import { API_BASE_URL } from "@/lib/config";
import type {
  FinalEventCard,
  EventSearchResponse,
  Theme,
  Sector,
  HealthResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: string,
  ) {
    super(`API ${status}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}

export function buildSearchUrl(q: string): string {
  const params = new URLSearchParams({ q });
  return `/api/events/search?${params.toString()}`;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  listEvents: () => request<FinalEventCard[]>("/api/events"),

  getEvent: (id: string) => request<FinalEventCard>(`/api/events/${id}`),

  search: (q: string) =>
    request<EventSearchResponse>(buildSearchUrl(q)),

  listThemes: () => request<Theme[]>("/api/themes"),

  themeEvents: (id: string) =>
    request<FinalEventCard[]>(`/api/themes/${id}/events`),

  listSectors: () => request<Sector[]>("/api/sectors"),

  sectorEvents: (id: string) =>
    request<FinalEventCard[]>(`/api/sectors/${id}/events`),
};
