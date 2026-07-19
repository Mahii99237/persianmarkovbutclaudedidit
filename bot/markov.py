"""
Trigram (lookback = 2) Markov chain that lives in Postgres.

Training and generation both go through the DB layer in db.py, so the bot
process itself is stateless — any number of bot workers could point at the
same database.
"""

from __future__ import annotations

import random
from typing import List, Optional

from . import db
from .persian_utils import END, START, detokenize, sentences_to_trigrams, tokenize_sentence


MAX_GEN_TOKENS = 40  # sentences longer than this get truncated at a soft stop


def learn(chat_id: int, text: str) -> int:
    """Ingest a raw Persian message into the model. Returns number of trigrams stored."""
    trigrams = list(sentences_to_trigrams(text))
    if not trigrams:
        return 0
    db.upsert_trigrams(chat_id, trigrams)
    return len(trigrams)


def _weighted_choice(candidates):
    """Pick a token from [(token, weight), ...] weighted by weight."""
    if not candidates:
        return None
    tokens = [t for t, _ in candidates]
    weights = [w for _, w in candidates]
    return random.choices(tokens, weights=weights, k=1)[0]


def generate(chat_id: int, seed_text: Optional[str] = None) -> Optional[str]:
    """
    Generate one sentence.

    If `seed_text` is provided, we try to start the chain from the last two
    tokens of the seed so the reply feels topical. Falls back to a normal
    sentence start (START, START) if the seed prefix isn't in the model.
    """
    if not db.has_any_trigrams(chat_id):
        return None

    w1: str
    w2: str
    output: List[str] = []

    if seed_text:
        seed_tokens = tokenize_sentence(seed_text)
        started_from_seed = False
        # Try prefixes from the seed, most-recent-two first, then walk back.
        for i in range(len(seed_tokens) - 1, 0, -1):
            cand_w1 = seed_tokens[i - 1]
            cand_w2 = seed_tokens[i]
            if db.next_candidates(chat_id, cand_w1, cand_w2):
                w1, w2 = cand_w1, cand_w2
                output = [w1, w2]
                started_from_seed = True
                break
        if not started_from_seed:
            w1, w2 = START, START
    else:
        w1, w2 = START, START

    for _ in range(MAX_GEN_TOKENS):
        candidates = db.next_candidates(chat_id, w1, w2)
        if not candidates:
            break
        nxt = _weighted_choice(candidates)
        if nxt == END:
            break
        output.append(nxt)
        w1, w2 = w2, nxt

    # If we truncated at the token cap, try to run a couple more steps
    # looking for a natural END to avoid mid-thought cutoffs.
    else:
        for _ in range(6):
            candidates = db.next_candidates(chat_id, w1, w2)
            if not candidates:
                break
            nxt = _weighted_choice(candidates)
            if nxt == END:
                break
            output.append(nxt)
            w1, w2 = w2, nxt

    sentence = detokenize(output)
    return sentence or None
