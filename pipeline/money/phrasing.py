"""Comparisons in words (contract C1): how one figure compares with another, said the way people say it.

ratio_words(a, b) turns a / b into words that sit before a noun phrase: "raised {words} Hackney's typical PTA"
gives "raised about double Hackney's typical PTA". It returns None when either value is missing, not a number,
zero or negative, so a caller says nothing rather than something misleading. assets/wrapped.js and assets/deck.js
carry the same bands as ratioWords(a, b); data/phrasing_cases.json is the table all three are tested against.
"""

from __future__ import annotations

import math

# (lowest ratio, whether that edge is included, words), checked from the top down.
BANDS = [
    (2.25, True, "about two and a half times"),
    (1.75, True, "about double"),
    (1.42, True, "about half as much again as"),
    (1.29, True, "about a third more than"),
    (1.15, False, "about a quarter more than"),
    (1.05, False, "a little more than"),
    (0.95, True, "about the same as"),
    (0.85, True, "a little less than"),
    (0.71, True, "about three-quarters of"),
    (0.58, True, "about two-thirds of"),
    (0.42, True, "about half"),
    (0.29, True, "about a third of"),
    (0.21, True, "about a quarter of"),
]
TIMES_FROM = 2.75


def _positive(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def ratio_words(a, b) -> str | None:
    """Words for a / b ('about double', 'a little less than', 'about 3 times'), or None when it can't be said."""
    a, b = _positive(a), _positive(b)
    if a is None or b is None:
        return None
    r = a / b
    if r >= TIMES_FROM:
        # Halves round up, as the browser's Math.round does, so Python and JS say the same number.
        return f"about {max(3, math.floor(r + 0.5))} times"
    for low, inclusive, words in BANDS:
        if r > low or (inclusive and r == low):
            return words
    return "under a quarter of"
