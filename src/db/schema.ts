import {
  bigint,
  bigserial,
  boolean,
  index,
  integer,
  pgTable,
  real,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

// One row per Telegram chat the bot has been added to.
// The Python bot and the Next.js dashboard both read/write this table.
export const chats = pgTable("chats", {
  chatId: bigint("chat_id", { mode: "number" }).primaryKey(),
  title: text("title"),
  username: text("username"),
  type: text("type"), // "private" | "group" | "supergroup" | "channel"
  learningEnabled: boolean("learning_enabled").notNull().default(true),
  // Probability (0..1) of speaking up on any non-triggered message.
  // Set to 0 to only reply when directly addressed.
  replyProbability: real("reply_probability").notNull().default(0.02),
  // Message-count based random speaking: bot picks a threshold in
  // [randomIntervalMin, randomIntervalMax] and speaks once messagesSinceRandom hits it.
  randomIntervalMin: integer("random_interval_min").notNull().default(40),
  randomIntervalMax: integer("random_interval_max").notNull().default(120),
  messagesSinceRandom: integer("messages_since_random").notNull().default(0),
  nextRandomThreshold: integer("next_random_threshold").notNull().default(60),
  totalMessagesLearned: integer("total_messages_learned").notNull().default(0),
  totalGenerations: integer("total_generations").notNull().default(0),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

// Trigram model: (w1, w2) -> w3 with occurrence count, scoped per chat.
// Sentence boundaries are represented with the literal sentinel tokens
// "__START__" and "__END__" which the Python side inserts around each
// tokenized sentence. That lets us:
//   * pick natural sentence beginnings by querying w1 = w2 = "__START__"
//   * stop generation cleanly when we emit "__END__"
export const trigrams = pgTable(
  "trigrams",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    chatId: bigint("chat_id", { mode: "number" }).notNull(),
    w1: text("w1").notNull(),
    w2: text("w2").notNull(),
    w3: text("w3").notNull(),
    count: integer("count").notNull().default(1),
  },
  (t) => [
    uniqueIndex("trigrams_chat_w1_w2_w3_uniq").on(t.chatId, t.w1, t.w2, t.w3),
    index("trigrams_chat_prefix_idx").on(t.chatId, t.w1, t.w2),
  ]
);

// A rolling log of the last N raw messages the bot has ingested per chat.
// Useful for the dashboard preview and for the /forget command.
export const messagesLog = pgTable(
  "messages_log",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    chatId: bigint("chat_id", { mode: "number" }).notNull(),
    userId: bigint("user_id", { mode: "number" }),
    username: text("username"),
    text: text("text").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("messages_log_chat_time_idx").on(t.chatId, t.createdAt)]
);
