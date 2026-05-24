import { adminFetch } from "@/lib/api/server";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const out = await adminFetch(`/api/admin/raw-events/${id}/requeue`, {
    method: "POST",
  });
  return Response.json(out);
}
