import { adminFetch } from "@/lib/api/server";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const out = await adminFetch("/api/admin/search/reindex", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dry_run: !!body.dry_run, limit: body.limit ?? 1000 }),
  });
  return Response.json(out);
}
