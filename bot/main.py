"""
Persian Trigram Markov Telegram bot.

Runs a long-polling Telegram bot that:
  * learns from every message in every chat it's in (if learning is enabled)
  * replies when someone replies to it or @-mentions it
  * occasionally speaks up on its own based on a *message-count* counter
    (never a wall-clock timer, per the design spec)

All state lives in Postgres. The schema is managed by the Next.js side
(Drizzle) — see ../src/db/schema.ts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
from typing import Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Support both `python -m bot.main` and `python bot/main.py`.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from bot import db, markov  # type: ignore
    from bot.persian_utils import normalize  # type: ignore
else:
    from . import db, markov
    from .persian_utils import normalize


load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("markov-bot")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
DEFAULT_RAND_MIN = int(os.environ.get("DEFAULT_RANDOM_MIN", "40"))
DEFAULT_RAND_MAX = int(os.environ.get("DEFAULT_RANDOM_MAX", "120"))

# Persian help text
HELP_TEXT = (
    "سلام! من یک ربات مارکوف فارسی هستم که از پیام‌های این گروه یاد می‌گیرم "
    "و گاهی خودم هم حرف می‌زنم.\n\n"
    "دستورها:\n"
    "/help — همین راهنما\n"
    "/stats — آمار یادگیری این گروه\n"
    "/say — همین الان یک جمله بساز\n"
    "/enable و /disable — روشن یا خاموش کردن یادگیری\n"
    "/prob <0..1> — احتمال حرف زدن خودجوش (مثلاً /prob 0.05)\n"
    "/interval <min> <max> — بازهٔ تعداد پیام برای حرف زدن تصادفی\n"
    "/forget — پاک کردن کامل حافظهٔ ربات در این چت (فقط ادمین)\n"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _remember_chat(update: Update) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    db.ensure_chat(
        chat_id=chat.id,
        title=chat.title,
        username=chat.username,
        chat_type=chat.type,
        default_min=DEFAULT_RAND_MIN,
        default_max=DEFAULT_RAND_MAX,
    )


def _is_addressed_to_bot(update: Update, bot_username: Optional[str]) -> bool:
    msg = update.effective_message
    if msg is None:
        return False
    # Replied to a bot message?
    if msg.reply_to_message and msg.reply_to_message.from_user \
            and msg.reply_to_message.from_user.is_bot \
            and bot_username \
            and msg.reply_to_message.from_user.username \
            and msg.reply_to_message.from_user.username.lower() == bot_username.lower():
        return True
    # @-mentioned in text?
    text = msg.text or msg.caption or ""
    if bot_username and f"@{bot_username.lower()}" in text.lower():
        return True
    return False


async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return False
    if chat.type == ChatType.PRIVATE:
        return True
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:  # noqa: BLE001
        return False


async def _generate_and_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    seed_text: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    sentence = markov.generate(chat.id, seed_text=seed_text)
    if not sentence:
        return
    db.bump_generations(chat.id)
    try:
        await context.bot.send_chat_action(chat.id, ChatAction.TYPING)
    except Exception:  # noqa: BLE001
        pass
    await context.bot.send_message(
        chat_id=chat.id,
        text=sentence,
        reply_to_message_id=reply_to_message_id,
        allow_sending_without_reply=True,
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    await update.effective_message.reply_text(HELP_TEXT)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    await update.effective_message.reply_text(HELP_TEXT)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    chat = update.effective_chat
    stats = db.chat_stats(chat.id)
    c = stats["chat"] or {}
    text = (
        f"📊 آمار گروه «{c.get('title') or chat.title or '—'}»:\n"
        f"• وضعیت یادگیری: {'روشن ✅' if c.get('learning_enabled') else 'خاموش ⛔'}\n"
        f"• پیام‌های یادگرفته‌شده: {c.get('total_messages_learned', 0)}\n"
        f"• تعداد ترای‌گرام‌ها: {stats['trigram_count']}\n"
        f"• واژگان یکتا: {stats['vocab']}\n"
        f"• تعداد جمله‌های تولیدشده: {c.get('total_generations', 0)}\n"
        f"• احتمال حرف زدن خودجوش: {c.get('reply_probability', 0):.3f}\n"
        f"• بازهٔ حرف زدن تصادفی: هر "
        f"{c.get('random_interval_min')}–{c.get('random_interval_max')} پیام\n"
        f"• شمارندهٔ فعلی: {c.get('messages_since_random', 0)}"
        f" / {c.get('next_random_threshold', 0)}"
    )
    await update.effective_message.reply_text(text)


async def cmd_say(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    seed = " ".join(context.args) if context.args else None
    chat = update.effective_chat
    if not db.has_any_trigrams(chat.id):
        await update.effective_message.reply_text(
            "هنوز چیزی یاد نگرفته‌ام. کمی حرف بزنید تا مدل پر شود."
        )
        return
    await _generate_and_send(update, context, seed_text=seed)


async def cmd_enable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    if not await _is_admin(update, context):
        await update.effective_message.reply_text("فقط ادمین‌ها اجازه دارند.")
        return
    db.set_learning_enabled(update.effective_chat.id, True)
    await update.effective_message.reply_text("یادگیری روشن شد ✅")


async def cmd_disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    if not await _is_admin(update, context):
        await update.effective_message.reply_text("فقط ادمین‌ها اجازه دارند.")
        return
    db.set_learning_enabled(update.effective_chat.id, False)
    await update.effective_message.reply_text("یادگیری خاموش شد ⛔")


async def cmd_prob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    if not await _is_admin(update, context):
        await update.effective_message.reply_text("فقط ادمین‌ها اجازه دارند.")
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /prob 0.05")
        return
    try:
        p = float(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("عدد نامعتبر.")
        return
    p = max(0.0, min(1.0, p))
    db.set_reply_probability(update.effective_chat.id, p)
    await update.effective_message.reply_text(f"احتمال حرف زدن خودجوش روی {p:.3f} تنظیم شد.")


async def cmd_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    if not await _is_admin(update, context):
        await update.effective_message.reply_text("فقط ادمین‌ها اجازه دارند.")
        return
    if len(context.args) != 2:
        await update.effective_message.reply_text("استفاده: /interval 40 120")
        return
    try:
        lo = int(context.args[0])
        hi = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("اعداد نامعتبر.")
        return
    if lo < 1 or hi < lo:
        await update.effective_message.reply_text("مقدارها منطقی نیستند.")
        return
    db.set_random_interval(update.effective_chat.id, lo, hi)
    await update.effective_message.reply_text(
        f"بازه روی {lo}–{hi} پیام تنظیم شد و شمارنده صفر شد."
    )


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_chat(update)
    if not await _is_admin(update, context):
        await update.effective_message.reply_text("فقط ادمین‌ها اجازه دارند.")
        return
    n = db.forget_chat(update.effective_chat.id)
    await update.effective_message.reply_text(f"حافظه پاک شد. ({n} ترای‌گرام حذف شد)")


# ---------------------------------------------------------------------------
# Main message handler: learn + maybe reply
# ---------------------------------------------------------------------------

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    text = msg.text or msg.caption
    if not text:
        return
    text = normalize(text).strip()
    if not text:
        return

    await _remember_chat(update)

    chat_row = db.get_chat(chat.id) or {}
    learning_enabled = chat_row.get("learning_enabled", True)
    reply_probability = float(chat_row.get("reply_probability", 0.02))

    # 1) Learn (unless disabled). We don't learn from commands.
    if learning_enabled and not text.startswith("/"):
        try:
            n = markov.learn(chat.id, text)
            if n:
                db.bump_messages_learned(chat.id, 1)
                db.log_message(
                    chat.id,
                    msg.from_user.id if msg.from_user else None,
                    msg.from_user.username if msg.from_user else None,
                    text,
                )
        except Exception:  # noqa: BLE001
            log.exception("failed to learn from message")

    # 2) Decide whether to speak.
    bot_username = context.bot.username
    addressed = _is_addressed_to_bot(update, bot_username)

    should_reply = False
    reply_to_id: Optional[int] = None

    if addressed:
        should_reply = True
        reply_to_id = msg.message_id
    elif chat.type == ChatType.PRIVATE:
        # In DMs, always try to reply.
        should_reply = True
        reply_to_id = msg.message_id
    else:
        # Random-per-message probability.
        if reply_probability > 0 and random.random() < reply_probability:
            should_reply = True

        # Message-count-based random speaking (never timer-based).
        # Only ticks in groups so DMs don't double-fire.
        fired, _ = db.tick_random_counter(chat.id)
        if fired:
            should_reply = True

    if should_reply:
        try:
            await _generate_and_send(
                update, context, seed_text=text, reply_to_message_id=reply_to_id
            )
        except Exception:  # noqa: BLE001
            log.exception("failed to generate/send")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _post_init(app: Application) -> None:
    me = await app.bot.get_me()
    log.info("Bot online as @%s (id=%s)", me.username, me.id)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Put it in .env or export it."
        )

    db.init_pool()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("say", cmd_say))
    application.add_handler(CommandHandler("enable", cmd_enable))
    application.add_handler(CommandHandler("disable", cmd_disable))
    application.add_handler(CommandHandler("prob", cmd_prob))
    application.add_handler(CommandHandler("interval", cmd_interval))
    application.add_handler(CommandHandler("forget", cmd_forget))

    # Everything that isn't a command.
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
    )
    application.add_handler(
        MessageHandler(filters.CAPTION & ~filters.COMMAND, on_message)
    )

    log.info("Starting long polling…")
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.getLogger().exception("bot crashed")
        raise
