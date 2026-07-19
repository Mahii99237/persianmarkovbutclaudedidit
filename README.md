# MarkovFa 🇮🇷 — Persian Trigram Markov Telegram Bot

A Telegram bot for Persian-speaking friend groups. It **listens** to messages,
learns them into a **trigram (2-word lookback) Markov chain**, and eventually
starts talking back — either when replied to / @-mentioned, or on its own
after a random number of messages have gone by (never on a timer).

Built with:

- 🐍 **Python 3** + [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) for the bot
- 📝 [`hazm`](https://github.com/roshan-research/hazm) for proper Persian tokenization (ZWNJ / half-space aware, Persian punctuation aware)
- 🐘 **PostgreSQL** for the shared model store
- ⚡ **Next.js 16** + Drizzle ORM for an RTL admin dashboard

---

## 1. One-line install (Ubuntu 22.04)

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/install.sh | sudo bash
```

The script:

1. Installs Python 3, Postgres 14, Node.js 20, build tools.
2. Clones the repo into `/opt/markov-fa` (override with `INSTALL_DIR=`).
3. Creates a Postgres role + database (`markov` / `markov_bot`).
4. Sets up a Python venv and `pip install -r bot/requirements.txt`.
5. `npm ci && npx drizzle-kit push && npm run build` for the dashboard.
6. Prompts for your `TELEGRAM_BOT_TOKEN` (or reads it from env).
7. Writes and enables two systemd units:
   - `markov-bot.service` — the Telegram bot (long-polling)
   - `markov-dashboard.service` — the Next.js dashboard on `:3000`

To pass secrets non-interactively:

```bash
TELEGRAM_BOT_TOKEN=123:ABC \
REPO_URL=https://github.com/<you>/<repo>.git \
curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/install.sh | sudo -E bash
```

Re-running the script is safe — it's idempotent and will `git pull` on update.

Useful commands after install:

```bash
systemctl status markov-bot
systemctl status markov-dashboard
journalctl -u markov-bot -f
```

---

## 2. Persian text handling — what the bot actually does

Persian is RTL and uses the **Zero-Width Non-Joiner** (`\u200c`, "half-space")
inside words like `می‌روم` and `کتاب‌ها`. A naive `text.split(" ")` breaks
those in half, so we go through **Hazm**:

```python
# bot/persian_utils.py
_normalizer      = hazm.Normalizer()
_sent_tokenizer  = hazm.SentenceTokenizer()
_word_tokenizer  = hazm.WordTokenizer(join_verb_parts=False)
```

Pipeline for every incoming message:

1. **Normalize** — unifies Arabic/Persian yeh/kaf variants, spacing, etc.
2. **Split into sentences** using Hazm's `SentenceTokenizer` (handles both
   `.` `!` `?` and Persian `؟`).
3. **Tokenize each sentence** with Hazm's `WordTokenizer` — this respects
   ZWNJ so multi-part words stay whole.
4. **Strip punctuation-only tokens** (English `?,.` and Persian `؟،؛` etc.)
   from the token stream, so they never enter the middle of a Markov trigram.
   Sentence-boundary punctuation is still *used*, just not *stored*.
5. **Pad with sentinels** and yield trigrams:
   ```
   [__START__, __START__, tok1, tok2, tok3, __END__]
     → (__START__, __START__, tok1)
     → (__START__, tok1, tok2)
     → (tok1, tok2, tok3)
     → (tok2, tok3, __END__)
   ```

Sentinels let generation start at natural sentence beginnings
(`w1 == w2 == __START__`) and stop cleanly at `__END__`.

---

## 3. When does the bot talk?

Configurable per chat via commands:

| Situation | Response |
|---|---|
| Someone **replies** to a bot message | Always responds (seeded from the message). |
| Someone **@mentions** the bot | Always responds. |
| Private chat (DM) | Always responds. |
| Random per-message chance | `reply_probability` (default `0.02`). |
| **Message-count random speaking** | Every chat has a running counter of messages since the bot last spoke on its own. A threshold is drawn uniformly from `[randomIntervalMin, randomIntervalMax]` (default 40–120). When the counter hits it, the bot speaks and re-rolls the threshold. **No wall-clock timers.** |

Bot commands (in Persian, all group-admin-gated where sensible):

| Command | Meaning |
|---|---|
| `/help` | Show the Persian help text. |
| `/stats` | Learning stats for this chat. |
| `/say [seed]` | Force-generate a sentence now (optionally seeded). |
| `/enable`, `/disable` | Toggle learning. |
| `/prob 0.05` | Set random per-message reply probability. |
| `/interval 40 120` | Set message-count random-speak window. |
| `/forget` | Wipe this chat's model. |

---

## 4. Manual / development setup

```bash
# clone
git clone https://github.com/<you>/<repo>.git markov-fa && cd markov-fa

# postgres
sudo -u postgres psql -c "CREATE ROLE markov LOGIN PASSWORD 'markov';"
sudo -u postgres createdb -O markov markov_bot

# schema
cp .env.example .env       # or edit .env to your DATABASE_URL
npm ci
npx drizzle-kit push

# python bot
python3 -m venv .venv
.venv/bin/pip install -r bot/requirements.txt
cp bot/.env.example bot/.env
# edit bot/.env — set TELEGRAM_BOT_TOKEN + DATABASE_URL
.venv/bin/python -m bot.main

# dashboard (separate terminal)
npm run dev
# open http://localhost:3000
```

---

## 5. Project layout

```
.
├── bot/                        # Python Telegram bot
│   ├── main.py                 # entry point (long polling)
│   ├── markov.py               # trigram learn/generate
│   ├── persian_utils.py        # Hazm tokenization + punctuation cleaning
│   ├── db.py                   # psycopg2 access to the shared DB
│   ├── requirements.txt
│   └── .env.example
├── src/
│   ├── db/schema.ts            # Drizzle schema (source of truth)
│   ├── db/index.ts             # pg pool + drizzle client
│   ├── lib/stats.ts            # aggregate queries for the dashboard
│   ├── lib/generate.ts         # TS mirror of the Markov walker
│   └── app/                    # Next.js App Router (RTL)
├── install.sh                  # one-line Ubuntu 22 installer
├── drizzle.config.json
└── README.md
```

---

## 6. Notes on Persian correctness

- We keep ZWNJ (`\u200c`) **inside** tokens — Hazm's `WordTokenizer` does the
  right thing. We only strip *invisible characters that aren't ZWNJ*
  (ZWSP, RLM, LRM, BOM, etc.) from the edges.
- Punctuation is cleaned from token edges, so `کتاب،` becomes `کتاب` before
  entering the model.
- The dashboard's `<html lang="fa" dir="rtl">` ensures every generated
  sentence renders in the correct direction.

---

## License

MIT. Have fun. Please don't feed it anything you wouldn't want your friends
to see repeated back at 2am.
