import { adminFetch } from "@/lib/api/server";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await req.json().catch(() => ({ force: false }));
  const out = await adminFetch(`/api/admin/raw-events/${id}/requeue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force: !!body.force }),
  });
  return Response.json(out);
}
