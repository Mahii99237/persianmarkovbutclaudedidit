"""
Thin PostgreSQL layer used by the bot. Shares its schema with the Next.js
dashboard (see ../src/db/schema.ts) — schema is created/updated on the
Node side via `npx drizzle-kit push`, so we never CREATE TABLE here.
"""

from __future__ import annotations

import logging
import os
import random
from contextlib import contextmanager
from typing import Iterable, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

log = logging.getLogger(__name__)

_pool: Optional[ThreadedConnectionPool] = None


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    _pool = ThreadedConnectionPool(minconn=1, maxconn=8, dsn=dsn)
    log.info("Postgres pool initialized")


@contextmanager
def _conn():
    assert _pool is not None, "init_pool() must be called first"
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


# ---------------------------------------------------------------------------
# chats
# ---------------------------------------------------------------------------

def ensure_chat(
    chat_id: int,
    title: Optional[str],
    username: Optional[str],
    chat_type: Optional[str],
    default_min: int,
    default_max: int,
) -> None:
    threshold = random.randint(default_min, default_max)
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chats (chat_id, title, username, type,
                               random_interval_min, random_interval_max,
                               next_random_threshold)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chat_id) DO UPDATE
              SET title = EXCLUDED.title,
                  username = EXCLUDED.username,
                  type = EXCLUDED.type,
                  updated_at = now()
            """,
            (chat_id, title, username, chat_type,
             default_min, default_max, threshold),
        )


def get_chat(chat_id: int) -> Optional[dict]:
    with _conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM chats WHERE chat_id = %s", (chat_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def set_learning_enabled(chat_id: int, enabled: bool) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE chats SET learning_enabled = %s, updated_at = now() WHERE chat_id = %s",
            (enabled, chat_id),
        )


def set_reply_probability(chat_id: int, p: float) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE chats SET reply_probability = %s, updated_at = now() WHERE chat_id = %s",
            (p, chat_id),
        )


def set_random_interval(chat_id: int, lo: int, hi: int) -> None:
    threshold = random.randint(lo, hi)
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """UPDATE chats SET random_interval_min = %s,
                                random_interval_max = %s,
                                next_random_threshold = %s,
                                messages_since_random = 0,
                                updated_at = now()
                 WHERE chat_id = %s""",
            (lo, hi, threshold, chat_id),
        )


def bump_messages_learned(chat_id: int, n: int) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE chats SET total_messages_learned = total_messages_learned + %s, "
            "updated_at = now() WHERE chat_id = %s",
            (n, chat_id),
        )


def bump_generations(chat_id: int) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE chats SET total_generations = total_generations + 1, "
            "updated_at = now() WHERE chat_id = %s",
            (chat_id,),
        )


def tick_random_counter(chat_id: int) -> Tuple[bool, int]:
    """
    Increment the messages-since-random counter. If the new value has hit
    the current threshold, reset it (picking a new threshold) and return
    (True, new_threshold). Otherwise return (False, current_threshold).
    """
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT messages_since_random, next_random_threshold, "
            "random_interval_min, random_interval_max "
            "FROM chats WHERE chat_id = %s FOR UPDATE",
            (chat_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False, 0
        msgs, threshold, lo, hi = row
        msgs += 1
        if msgs >= threshold:
            new_threshold = random.randint(max(1, lo), max(1, hi))
            cur.execute(
                "UPDATE chats SET messages_since_random = 0, "
                "next_random_threshold = %s, updated_at = now() "
                "WHERE chat_id = %s",
                (new_threshold, chat_id),
            )
            return True, new_threshold
        cur.execute(
            "UPDATE chats SET messages_since_random = %s, updated_at = now() "
            "WHERE chat_id = %s",
            (msgs, chat_id),
        )
        return False, threshold


# ---------------------------------------------------------------------------
# trigrams
# ---------------------------------------------------------------------------

def upsert_trigrams(chat_id: int, trigrams: Iterable[Tuple[str, str, str]]) -> int:
    """Bulk upsert trigrams for a chat; returns number of rows touched."""
    trigrams = list(trigrams)
    if not trigrams:
        return 0
    values = [(chat_id, w1, w2, w3) for (w1, w2, w3) in trigrams]
    with _conn() as c, c.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO trigrams (chat_id, w1, w2, w3, count)
            VALUES %s
            ON CONFLICT (chat_id, w1, w2, w3)
              DO UPDATE SET count = trigrams.count + 1
            """,
            [(cid, w1, w2, w3, 1) for (cid, w1, w2, w3) in values],
            template="(%s, %s, %s, %s, %s)",
        )
    return len(values)


def next_candidates(chat_id: int, w1: str, w2: str) -> List[Tuple[str, int]]:
    """Return list of (w3, count) continuations for the given prefix."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT w3, count FROM trigrams "
            "WHERE chat_id = %s AND w1 = %s AND w2 = %s",
            (chat_id, w1, w2),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def has_any_trigrams(chat_id: int) -> bool:
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT 1 FROM trigrams WHERE chat_id = %s LIMIT 1", (chat_id,))
        return cur.fetchone() is not None


def forget_chat(chat_id: int) -> int:
    with _conn() as c, c.cursor() as cur:
        cur.execute("DELETE FROM trigrams WHERE chat_id = %s", (chat_id,))
        deleted = cur.rowcount
        cur.execute("DELETE FROM messages_log WHERE chat_id = %s", (chat_id,))
        cur.execute(
            "UPDATE chats SET total_messages_learned = 0, "
            "total_generations = 0, messages_since_random = 0, "
            "updated_at = now() WHERE chat_id = %s",
            (chat_id,),
        )
        return deleted


def chat_stats(chat_id: int) -> dict:
    with _conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM chats WHERE chat_id = %s", (chat_id,))
        chat = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) AS trigram_count, COALESCE(SUM(count),0) AS token_events "
            "FROM trigrams WHERE chat_id = %s",
            (chat_id,),
        )
        agg = cur.fetchone()
        cur.execute(
            "SELECT COUNT(DISTINCT w3) AS vocab FROM trigrams "
            "WHERE chat_id = %s AND w3 <> '__END__'",
            (chat_id,),
        )
        vocab = cur.fetchone()
        return {
            "chat": dict(chat) if chat else None,
            "trigram_count": int(agg["trigram_count"]) if agg else 0,
            "token_events": int(agg["token_events"]) if agg else 0,
            "vocab": int(vocab["vocab"]) if vocab else 0,
        }


# ---------------------------------------------------------------------------
# messages_log (rolling window, we keep it small)
# ---------------------------------------------------------------------------

MAX_LOG_PER_CHAT = 500


def log_message(chat_id: int, user_id: Optional[int], username: Optional[str], text: str) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO messages_log (chat_id, user_id, username, text) "
            "VALUES (%s, %s, %s, %s)",
            (chat_id, user_id, username, text),
        )
        # Trim oldest rows past MAX_LOG_PER_CHAT.
        cur.execute(
            """
            DELETE FROM messages_log
            WHERE chat_id = %s AND id IN (
              SELECT id FROM messages_log
              WHERE chat_id = %s
              ORDER BY id DESC
              OFFSET %s
            )
            """,
            (chat_id, chat_id, MAX_LOG_PER_CHAT),
        )
