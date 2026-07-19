import { desc, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import { chats, trigrams, messagesLog } from "@/db/schema";

export type ChatSummary = {
  chatId: number;
  title: string | null;
  username: string | null;
  type: string | null;
  learningEnabled: boolean;
  replyProbability: number;
  randomIntervalMin: number;
  randomIntervalMax: number;
  messagesSinceRandom: number;
  nextRandomThreshold: number;
  totalMessagesLearned: number;
  totalGenerations: number;
  trigramCount: number;
  vocab: number;
};

export type TopTrigram = {
  w1: string;
  w2: string;
  w3: string;
  count: number;
};

export async function getGlobalStats() {
  const [chatCountRow] = await db
    .select({ n: sql<number>`count(*)::int` })
    .from(chats);
  const [trigramCountRow] = await db
    .select({ n: sql<number>`count(*)::int` })
    .from(trigrams);
  const [vocabRow] = await db
    .select({ n: sql<number>`count(distinct ${trigrams.w3})::int` })
    .from(trigrams)
    .where(sql`${trigrams.w3} <> '__END__'`);
  const [messagesRow] = await db
    .select({ n: sql<number>`coalesce(sum(${chats.totalMessagesLearned}), 0)::int` })
    .from(chats);
  const [genRow] = await db
    .select({ n: sql<number>`coalesce(sum(${chats.totalGenerations}), 0)::int` })
    .from(chats);
  return {
    chats: chatCountRow?.n ?? 0,
    trigrams: trigramCountRow?.n ?? 0,
    vocab: vocabRow?.n ?? 0,
    messagesLearned: messagesRow?.n ?? 0,
    generations: genRow?.n ?? 0,
  };
}

export async function getChatSummaries(): Promise<ChatSummary[]> {
  const rows = await db
    .select({
      chatId: chats.chatId,
      title: chats.title,
      username: chats.username,
      type: chats.type,
      learningEnabled: chats.learningEnabled,
      replyProbability: chats.replyProbability,
      randomIntervalMin: chats.randomIntervalMin,
      randomIntervalMax: chats.randomIntervalMax,
      messagesSinceRandom: chats.messagesSinceRandom,
      nextRandomThreshold: chats.nextRandomThreshold,
      totalMessagesLearned: chats.totalMessagesLearned,
      totalGenerations: chats.totalGenerations,
      trigramCount: sql<number>`(
        select count(*)::int from ${trigrams} t
        where t.chat_id = ${chats.chatId}
      )`,
      vocab: sql<number>`(
        select count(distinct t.w3)::int from ${trigrams} t
        where t.chat_id = ${chats.chatId} and t.w3 <> '__END__'
      )`,
    })
    .from(chats)
    .orderBy(desc(chats.totalMessagesLearned));
  return rows;
}

export async function getTopTrigrams(chatId: number, limit = 15): Promise<TopTrigram[]> {
  return db
    .select({
      w1: trigrams.w1,
      w2: trigrams.w2,
      w3: trigrams.w3,
      count: trigrams.count,
    })
    .from(trigrams)
    .where(
      sql`${trigrams.chatId} = ${chatId}
        and ${trigrams.w1} <> '__START__'
        and ${trigrams.w2} <> '__START__'
        and ${trigrams.w3} <> '__END__'`
    )
    .orderBy(desc(trigrams.count))
    .limit(limit);
}

export async function getRecentMessages(chatId: number, limit = 10) {
  return db
    .select({
      id: messagesLog.id,
      username: messagesLog.username,
      text: messagesLog.text,
      createdAt: messagesLog.createdAt,
    })
    .from(messagesLog)
    .where(eq(messagesLog.chatId, chatId))
    .orderBy(desc(messagesLog.id))
    .limit(limit);
}
