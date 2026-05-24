import "server-only";
import { INTERNAL_API_BASE_URL } from "@/lib/config";

const TOKEN = process.env.ADMIN_API_TOKEN ?? "";

export async function adminFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers as HeadersInit | undefined);
  if (TOKEN) headers.set("X-Admin-Token", TOKEN);
  const res = await fetch(`${INTERNAL_API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`admin api ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}
