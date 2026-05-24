import { adminFetch } from "@/lib/api/server";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const out = await adminFetch("/api/admin/reconcile-stuck", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dry_run: !!body.dry_run }),
  });
  return Response.json(out);
}
