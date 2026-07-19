import { getChatSummaries, getGlobalStats } from "@/lib/stats";

export const dynamic = "force-dynamic";

export async function GET() {
  const [global, list] = await Promise.all([getGlobalStats(), getChatSummaries()]);
  return Response.json({ ok: true, global, chats: list });
}
