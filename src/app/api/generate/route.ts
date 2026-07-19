import { NextRequest } from "next/server";
import { generateSentence } from "@/lib/generate";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const chatIdRaw = url.searchParams.get("chatId");
  const chatId = chatIdRaw ? Number(chatIdRaw) : NaN;
  if (!Number.isFinite(chatId)) {
    return Response.json({ ok: false, error: "chatId required" }, { status: 400 });
  }
  try {
    const sentence = await generateSentence(chatId);
    if (!sentence) {
      return Response.json({ ok: true, sentence: null, empty: true });
    }
    return Response.json({ ok: true, sentence });
  } catch (e) {
    return Response.json(
      { ok: false, error: e instanceof Error ? e.message : "unknown" },
      { status: 500 }
    );
  }
}
