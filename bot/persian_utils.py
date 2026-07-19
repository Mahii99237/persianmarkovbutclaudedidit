"""
Persian text preprocessing for the Markov bot.

Persian is RTL and uses the Zero-Width Non-Joiner (ZWNJ, U+200C, "half-space")
to join morphemes inside a single word (e.g. "می‌روم", "کتاب‌ها"). A naive
`text.split(" ")` will happily rip those words apart, so we use Hazm's
tokenizers which respect Persian orthography.

We keep sentence-ending punctuation as *structural markers* — they are used
by SentenceTokenizer to split messages into sentences, but they are then
stripped from the individual tokens so we never store "کتاب،" or "خوبی؟"
as a token.
"""

from __future__ import annotations

import re
from typing import List

from hazm import Normalizer, SentenceTokenizer, WordTokenizer

# Sentinels that mark the beginning and end of a sentence in the Markov model.
# Chosen so they can never collide with real Persian tokens.
START = "__START__"
END = "__END__"

# ZWNJ (half-space) — must be preserved inside words.
ZWNJ = "\u200c"

_normalizer = Normalizer()
_sent_tokenizer = SentenceTokenizer()
# join_verb_parts=True keeps multi-part verbs like "خواهم رفت" reasonable;
# replace_hashtags/replace_emails/etc default to False which is what we want
# because we want the bot to be able to learn user mentions and hashtags too.
_word_tokenizer = WordTokenizer(join_verb_parts=False)

# Characters that count as "just punctuation" and should never appear as a
# standalone Markov token. We keep sentence-boundary punctuation (. ! ? ؟)
# out of the token stream because SentenceTokenizer has already used them
# to split. Persian comma "،" and semicolon "؛" are also dropped.
_PUNCT_CHARS = set(".،؛؟?!,:;\"'«»()[]{}—–…/\\|~`^*<>=+")

# Regex to detect a token that is purely punctuation / symbols / digits.
_ONLY_PUNCT_RE = re.compile(r"^[\W_]+$", flags=re.UNICODE)

# Zero-width chars we don't want (except ZWNJ, which we keep).
_STRIP_INVISIBLES = re.compile(r"[\u200b\u200d\u200e\u200f\ufeff]")


def _clean_token(tok: str) -> str:
    """Strip surrounding punctuation from a token without harming ZWNJ."""
    tok = _STRIP_INVISIBLES.sub("", tok)
    # Strip leading/trailing punctuation characters.
    tok = tok.strip("".join(_PUNCT_CHARS) + " \t\r\n")
    return tok


def _is_valid_token(tok: str) -> bool:
    if not tok:
        return False
    if _ONLY_PUNCT_RE.match(tok):
        return False
    return True


def normalize(text: str) -> str:
    """Normalize Persian text (unify Arabic/Persian yeh/kaf, spacing, etc)."""
    return _normalizer.normalize(text)


def split_sentences(text: str) -> List[str]:
    """Split raw Persian text into sentences using Hazm's SentenceTokenizer."""
    text = normalize(text)
    return [s.strip() for s in _sent_tokenizer.tokenize(text) if s.strip()]


def tokenize_sentence(sentence: str) -> List[str]:
    """
    Tokenize a single Persian sentence into clean tokens.
    Punctuation-only tokens are removed; ZWNJ inside words is preserved.
    """
    raw = _word_tokenizer.tokenize(sentence)
    out: List[str] = []
    for tok in raw:
        cleaned = _clean_token(tok)
        if _is_valid_token(cleaned):
            out.append(cleaned)
    return out


def sentences_to_trigrams(text: str):
    """
    Yield (w1, w2, w3) trigrams for every sentence in `text`, padded with
    START/END sentinels so we can sample sentence beginnings and know when
    to stop generating.

    Example for a sentence with tokens [A, B, C]:
        (START, START, A)
        (START, A, B)
        (A, B, C)
        (B, C, END)
    """
    for sent in split_sentences(text):
        tokens = tokenize_sentence(sent)
        if not tokens:
            continue
        padded = [START, START] + tokens + [END]
        for i in range(len(padded) - 2):
            yield padded[i], padded[i + 1], padded[i + 2]


def detokenize(tokens: List[str]) -> str:
    """
    Reassemble tokens into a Persian sentence. We simply join with a normal
    space — ZWNJs live *inside* tokens (thanks to Hazm) and don't need to
    be reintroduced between them.
    """
    return " ".join(t for t in tokens if t not in (START, END))
