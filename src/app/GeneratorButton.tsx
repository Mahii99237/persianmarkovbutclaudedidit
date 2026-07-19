"use client";

import { useState } from "react";

export function GeneratorButton({ chatId }: { chatId: number }) {
  const [loading, setLoading] = useState(false);
  const [sentence, setSentence] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    setEmpty(false);
    setSentence(null);
    try {
      const res = await fetch(`/api/generate?chatId=${chatId}`, { cache: "no-store" });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error ?? "خطا");
      } else if (data.empty) {
        setEmpty(true);
      } else {
        setSentence(data.sentence);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطای شبکه");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-3">
      <button
        onClick={generate}
        disabled={loading}
        className="inline-flex items-center gap-2 rounded-md bg-emerald-500/90 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed text-slate-900 font-semibold px-3 py-1.5 text-sm transition"
      >
        {loading ? "در حال ساخت…" : "یک جمله بساز"}
      </button>
      {sentence && (
        <p
          dir="rtl"
          className="mt-3 text-emerald-200 bg-emerald-950/40 border border-emerald-800/40 rounded-md px-3 py-2 leading-8"
        >
          {sentence}
        </p>
      )}
      {empty && (
        <p className="mt-3 text-sm text-amber-300">
          هنوز داده‌ای برای این چت وجود ندارد.
        </p>
      )}
      {error && <p className="mt-3 text-sm text-red-400">خطا: {error}</p>}
    </div>
  );
}
