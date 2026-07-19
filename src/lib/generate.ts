/**
 * TypeScript mirror of bot/markov.py used for the dashboard's "preview
 * generation" button. Reads from the exact same `trigrams` table that the
 * Python bot writes to, so the outputs match what the bot would say.
 */

import { and, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import { trigrams } from "@/db/schema";

const START = "__START__";
const END = "__END__";
const MAX_TOKENS = 40;

type Candidate = { w3: string; count: number };

async function nextCandidates(chatId: number, w1: string, w2: string): Promise<Candidate[]> {
  return db
    .select({ w3: trigrams.w3, count: trigrams.count })
    .from(trigrams)
    .where(
      and(
        eq(trigrams.chatId, chatId),
        eq(trigrams.w1, w1),
        eq(trigrams.w2, w2)
      )
    );
}

function weightedPick(cands: Candidate[]): string | null {
  if (cands.length === 0) return null;
  const total = cands.reduce((s, c) => s + c.count, 0);
  let r = Math.random() * total;
  for (const c of cands) {
    r -= c.count;
    if (r <= 0) return c.w3;
  }
  return cands[cands.length - 1].w3;
}

export async function generateSentence(chatId: number): Promise<string | null> {
  const [any] = await db
    .select({ n: sql<number>`1` })
    .from(trigrams)
    .where(eq(trigrams.chatId, chatId))
    .limit(1);
  if (!any) return null;

  let w1 = START;
  let w2 = START;
  const out: string[] = [];

  for (let i = 0; i < MAX_TOKENS; i++) {
    const cands = await nextCandidates(chatId, w1, w2);
    const next = weightedPick(cands);
    if (next === null || next === END) break;
    out.push(next);
    w1 = w2;
    w2 = next;
  }

  const sentence = out.filter((t) => t !== START && t !== END).join(" ");
  return sentence || null;
}
