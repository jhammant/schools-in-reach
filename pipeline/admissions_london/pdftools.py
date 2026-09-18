"""Word-geometry helpers shared by the secondary and primary admissions parsers.

Hackney's PDFs are laid out as visual tables, often two or three per page, with
blank cells. Plain text extraction loses the column a number belongs to, so the
parsers work on pdfplumber words (text + bounding box) and assign values to
columns by x-position and to rows by y-position.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# The 2018-2020 sections were exported with a font whose "ti"/"tt"/"ft"
# ligature glyphs have no unicode mapping; pdfplumber yields "\x00" for them.
_TT_WORDS = {"betty", "patten", "admitted", "matthias", "attend", "attends"}
_FT_WORDS = {"after"}


def fix_text(text: str) -> str:
    """Normalise ligatures, curly quotes and broken ligature glyphs."""
    text = unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'")
    if "\x00" in text:
        letters = re.sub(r"[^a-z\x00]", "", text.lower())
        for ligature, vocabulary in (("tt", _TT_WORDS), ("ft", _FT_WORDS)):
            if letters.replace("\x00", ligature) in vocabulary:
                return text.replace("\x00", ligature)
        text = text.replace("\x00", "ti")
    return text


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class Line:
    words: list[Word]

    @property
    def cy(self) -> float:
        return sum(w.cy for w in self.words) / len(self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def page_words(page) -> list[Word]:
    raw = page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)
    return [Word(fix_text(w["text"]), w["x0"], w["x1"], w["top"], w["bottom"]) for w in raw]


def group_lines(words: list[Word], tol: float = 3.0) -> list[Line]:
    lines: list[Line] = []
    for word in sorted(words, key=lambda w: (w.cy, w.x0)):
        if lines and abs(word.cy - lines[-1].cy) <= tol:
            lines[-1].words.append(word)
        else:
            lines.append(Line([word]))
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    return lines


def segments(line: Line, gap: float = 15.0) -> list[Line]:
    """Split a visual line into runs of words separated by wide gaps."""
    out: list[Line] = []
    for word in line.words:
        if out and word.x0 - out[-1].words[-1].x1 <= gap:
            out[-1].words.append(word)
        else:
            out.append(Line([word]))
    return out


@dataclass
class Region:
    header: Line
    x0: float
    x1: float
    y0: float
    y1: float

    def contains(self, word: Word) -> bool:
        return self.x0 <= word.cx < self.x1 and self.y0 <= word.cy < self.y1

    def words(self, words: list[Word]) -> list[Word]:
        return [w for w in words if self.contains(w)]


def build_regions(headers: list[Line], width: float, height: float,
                  pad: float = 10.0, row_tol: float = 20.0) -> list[Region]:
    """Give each block header the page area below it that belongs to it.

    A block extends down to the next header that overlaps it horizontally and
    right to the next header that starts on (roughly) the same row before the
    block ends. Both bounds depend on each other, so iterate to a fixed point.
    """
    n = len(headers)
    right = [width] * n
    bottom = [height] * n
    for _ in range(8):
        for i, h in enumerate(headers):
            below = [o.top for j, o in enumerate(headers)
                     if j != i and o.top > h.top + 5 and o.x0 < right[i] - pad and right[j] > h.x0 + pad]
            bottom[i] = min(below + [height])
        for i, h in enumerate(headers):
            beside = [o.x0 for j, o in enumerate(headers)
                      if j != i and o.x0 > h.x0 + 30 and h.top - row_tol < o.top < bottom[i]]
            right[i] = min(beside + [width])
    return [Region(h, h.x0 - pad, right[i] - pad, h.top - 3, bottom[i] - 3) for i, h in enumerate(headers)]


_NUM_RE = re.compile(r"^[*~^]*(\d+\.\d+|\.\d+|\d+)[*~^]*$")
_INT_RE = re.compile(r"^[*~^]*(\d+)[*~^]*$")


def is_number(text: str) -> bool:
    return _NUM_RE.match(text) is not None


def as_int(text: str) -> int | None:
    m = _INT_RE.match(text)
    return int(m.group(1)) if m else None


def as_float(text: str) -> float | None:
    m = _NUM_RE.match(text)
    return float(m.group(1)) if m else None


def nearest(value: float, centers: list[float]) -> tuple[int, float]:
    idx = min(range(len(centers)), key=lambda k: abs(centers[k] - value))
    return idx, abs(centers[idx] - value)
