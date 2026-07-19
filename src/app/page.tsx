import { getChatSummaries, getGlobalStats, getTopTrigrams } from "@/lib/stats";
import { GeneratorButton } from "./GeneratorButton";

export const dynamic = "force-dynamic";

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4">
      <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-bold text-slate-50 tabular-nums">{value}</div>
    </div>
  );
}

export default async function DashboardPage() {
  const [global, chats] = await Promise.all([getGlobalStats(), getChatSummaries()]);

  // Fetch top trigrams for up to the first 8 chats so the page stays fast.
  const topByChat = await Promise.all(
    chats.slice(0, 8).map(async (c) => ({
      chatId: c.chatId,
      top: await getTopTrigrams(c.chatId, 8),
    }))
  );
  const topMap = new Map(topByChat.map((x) => [x.chatId, x.top]));

  return (
    <main className="max-w-6xl mx-auto px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-extrabold text-emerald-300">
          MarkovFa 🇮🇷
        </h1>
        <p className="mt-2 text-slate-400 leading-7">
          داشبورد ربات تلگرام مارکوف فارسی — مدل ترای‌گرام (لُک‌بک ۲ کلمه) با
          پشتیبانی از نیم‌فاصله و توکن‌سازی مبتنی بر Hazm.
        </p>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-10">
        <StatCard label="تعداد چت‌ها" value={global.chats} />
        <StatCard label="پیام‌های یادگرفته" value={global.messagesLearned} />
        <StatCard label="ترای‌گرام‌ها" value={global.trigrams.toLocaleString("fa-IR")} />
        <StatCard label="واژگان یکتا" value={global.vocab.toLocaleString("fa-IR")} />
        <StatCard label="جمله‌های تولیدشده" value={global.generations} />
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-100 mb-4">چت‌ها</h2>
        {chats.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center text-slate-400">
            هنوز ربات به هیچ چتی اضافه نشده است. توکن ربات را در{" "}
            <code className="text-emerald-300">bot/.env</code> بگذارید،
            سرویس <code className="text-emerald-300">markov-bot</code> را
            راه‌اندازی کنید، و ربات را به گروه اضافه کنید.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {chats.map((c) => {
              const top = topMap.get(c.chatId) ?? [];
              return (
                <article
                  key={c.chatId}
                  className="rounded-xl bg-slate-900/60 border border-slate-800 p-5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-50">
                        {c.title || c.username || `چت ${c.chatId}`}
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {c.type} · id={c.chatId}
                      </p>
                    </div>
                    <span
                      className={`text-xs px-2 py-1 rounded-full border ${
                        c.learningEnabled
                          ? "border-emerald-700 text-emerald-300 bg-emerald-950/50"
                          : "border-red-800 text-red-300 bg-red-950/40"
                      }`}
                    >
                      {c.learningEnabled ? "یادگیری روشن" : "یادگیری خاموش"}
                    </span>
                  </div>

                  <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-slate-400">پیام‌ها</dt>
                      <dd className="text-slate-100 font-semibold tabular-nums">
                        {c.totalMessagesLearned}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">ترای‌گرام‌ها</dt>
                      <dd className="text-slate-100 font-semibold tabular-nums">
                        {c.trigramCount.toLocaleString("fa-IR")}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">واژگان</dt>
                      <dd className="text-slate-100 font-semibold tabular-nums">
                        {c.vocab.toLocaleString("fa-IR")}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">جمله‌های تولیدشده</dt>
                      <dd className="text-slate-100 font-semibold tabular-nums">
                        {c.totalGenerations}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">احتمال حرف زدن</dt>
                      <dd className="text-slate-100 font-semibold tabular-nums">
                        {c.replyProbability.toFixed(3)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">شمارندهٔ تصادفی</dt>
                      <dd className="text-slate-100 font-semibold tabular-nums">
                        {c.messagesSinceRandom} / {c.nextRandomThreshold}{" "}
                        <span className="text-slate-500 text-xs">
                          ({c.randomIntervalMin}–{c.randomIntervalMax})
                        </span>
                      </dd>
                    </div>
                  </dl>

                  {top.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-xs uppercase tracking-wider text-slate-400 mb-2">
                        پرتکرارترین ترای‌گرام‌ها
                      </h4>
                      <ul className="space-y-1 text-sm">
                        {top.map((t, i) => (
                          <li
                            key={i}
                            className="flex items-center justify-between gap-3 bg-slate-950/40 rounded px-2 py-1"
                          >
                            <span dir="rtl" className="text-slate-200">
                              {t.w1} {t.w2} {t.w3}
                            </span>
                            <span className="text-xs text-slate-400 tabular-nums">
                              ×{t.count}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <GeneratorButton chatId={c.chatId} />
                </article>
              );
            })}
          </div>
        )}
      </section>

      <footer className="mt-12 text-center text-xs text-slate-500">
        MarkovFa · Persian trigram Markov Telegram bot · Deployed on Ubuntu 22
      </footer>
    </main>
  );
}
