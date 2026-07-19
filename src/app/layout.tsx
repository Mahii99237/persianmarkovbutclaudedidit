import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "MarkovFa — Persian Markov Telegram Bot",
  description:
    "Dashboard for the Persian trigram Markov Telegram bot: per-chat learning stats, vocabulary size, and sample generations.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fa" dir="rtl">
      <body className="bg-slate-950 text-slate-100 antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
