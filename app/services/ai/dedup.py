"""Post-generation dedup for AI question sets.

The model (and any template fallback) can return the same question twice,
either verbatim or paraphrased. This module is the choke point: every
``generate_questions`` path runs its output through :func:`dedupe_mcqs` /
:func:`dedupe_essays` before returning, keeping the FIRST occurrence of each
distinct question and dropping the rest.

A question counts as a duplicate of an already-kept one when ANY of these
holds:

- the normalized stem is identical (case / punctuation / whitespace only
  differ), or
- stem token similarity (Jaccard over content words) is at or above
  :data:`SIMILARITY_THRESHOLD`, or
- (MCQ only) the normalized option-text SET is identical — the same four
  options in a different order is still the same item.

Threshold note: 0.5 was chosen so that a genuine paraphrase (same content
words, different filler) scores well above it, while two questions about
different sub-concepts of the same topic score well below it — they share the
topic word but little else. See ``tests/test_ai_question_generation.py``
for the fixtures that pin this behaviour.
"""

import re
from typing import FrozenSet, List, Sequence, Set

from app.schemas.question import (
    GeneratedQuestionEssay,
    GeneratedQuestionMCQ,
)

SIMILARITY_THRESHOLD = 0.5

# Generic Indonesian function words + question boilerplate. Deliberately
# SMALL: content words such as "contoh", "definisi", "dampak", "penyebab"
# and the cognitive verbs ("jelaskan", "bandingkan", "evaluasi") are what
# distinguish one angle from another, so they must stay in the token set.
_STOPWORDS: Set[str] = {
    "yang", "dan", "atau", "di", "ke", "dari", "dalam", "pada", "dengan",
    "untuk", "adalah", "merupakan", "tentang", "mengenai", "apakah",
    "bagaimana", "manakah", "berikut", "paling", "tepat", "benar", "jika",
    "apabila", "sebuah", "suatu", "tersebut", "ini", "itu", "secara",
    "juga", "dapat", "akan", "oleh", "sebagai", "apa", "diantara",
    "antara", "sangat", "lebih", "kurang", "tidak", "bukan", "tanpa",
    "sampai", "hingga", "saat", "ketika", "kemudian", "lalu", "maka",
    "sehingga", "karena", "hal", "setiap", "semua", "nomor", "butir",
    "pertanyaan", "jawaban", "opsi", "terhadap", "melalui", "menurut",
    "yaitu", "yakni", "ialah", "para", "nya", "salah", "satu", "dua",
    "tiga",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return " ".join(_TOKEN_RE.findall((text or "").lower()))


def stem_tokens(text: str) -> Set[str]:
    """Content-word token set of a stem (stopwords + 1-letter tokens out)."""
    return {t for t in normalize_text(text).split() if t not in _STOPWORDS and len(t) >= 2}


def stem_similarity(a: str, b: str) -> float:
    """Jaccard similarity of two stems over their content-word tokens."""
    ta, tb = stem_tokens(a), stem_tokens(b)
    if not ta or not tb:
        return 1.0 if normalize_text(a) == normalize_text(b) else 0.0
    return len(ta & tb) / len(ta | tb)


def _option_text_set(options: Sequence) -> FrozenSet[str]:
    return frozenset(
        normalize_text(getattr(o, "text", "") or "") for o in (options or [])
    )


def dedupe_mcqs(mcqs: List[GeneratedQuestionMCQ]) -> List[GeneratedQuestionMCQ]:
    """Drop exact + near-duplicate MCQs, keeping the first occurrence."""
    kept: List[GeneratedQuestionMCQ] = []
    kept_norms: List[str] = []
    kept_tokens: List[Set[str]] = []
    kept_option_sets: List[FrozenSet[str]] = []
    for q in mcqs:
        norm = normalize_text(q.prompt)
        toks = stem_tokens(q.prompt)
        opt_set = _option_text_set(q.options)
        duplicate = False
        for kn, kt, ko in zip(kept_norms, kept_tokens, kept_option_sets):
            if norm and norm == kn:
                duplicate = True
                break
            if toks and kt:
                inter = len(toks & kt)
                union = len(toks | kt)
                if union and inter / union >= SIMILARITY_THRESHOLD:
                    duplicate = True
                    break
            if opt_set and opt_set == ko:
                duplicate = True
                break
        if not duplicate:
            kept.append(q)
            kept_norms.append(norm)
            kept_tokens.append(toks)
            kept_option_sets.append(opt_set)
    return kept


def dedupe_essays(essays: List[GeneratedQuestionEssay]) -> List[GeneratedQuestionEssay]:
    """Drop exact + near-duplicate essay prompts, keeping the first occurrence."""
    kept: List[GeneratedQuestionEssay] = []
    kept_norms: List[str] = []
    kept_tokens: List[Set[str]] = []
    for q in essays:
        norm = normalize_text(q.prompt)
        toks = stem_tokens(q.prompt)
        duplicate = False
        for kn, kt in zip(kept_norms, kept_tokens):
            if norm and norm == kn:
                duplicate = True
                break
            if toks and kt:
                inter = len(toks & kt)
                union = len(toks | kt)
                if union and inter / union >= SIMILARITY_THRESHOLD:
                    duplicate = True
                    break
        if not duplicate:
            kept.append(q)
            kept_norms.append(norm)
            kept_tokens.append(toks)
    return kept
