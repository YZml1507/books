"""`booksec` — book/section addressing, the FOURTH scheme. Built for Herodotus.

Every figure in this docstring was measured on the main line against
data/raw_ext/generality/herodotus/pg2707.txt (895,283 chars), not taken from a report:

    ^BOOK [IVX]+\\.        4     @7315 @275453 @497355 @692853
    ^(\\d{1,3})\\.\\s      736   section number followed by a full stop
    ^(\\d{1,3}),\\s         28   section number followed by a COMMA
    ^(\\d{1,3})\\s         746   number with NO punctuation
    ^NOTES TO BOOK.*        4     @252252 @478317 @679174 @879306

Three decisions follow from those five lines, and each of them changes the answer:

1. THE COMMA FORM IS NOT OPTIONAL. 28 sections print as 「15, and I will speak now of
   Ardys」. Accepting only the full stop loses 27 of them. 736 + 28 = 764 against a canonical
   763 for Books I-IV (216/182/160/205).

2. THE UNPUNCTUATED FORM MUST BE REJECTED. 746 lines begin with a bare number and no
   punctuation, and they are footnote numbers wrapped to line start, not sections. Admitting
   them would roughly double the address space with rubbish. This is the same trap as U-05,
   where 「came unto Jeremiah.」 was accepted as a book heading: a pattern that merely *can*
   match a heading is not a heading test.

3. THE NOTES APPARATUS IS A SECOND ASCENDING CHAIN. Each book is followed by its own
   「NOTES TO BOOK n」 block whose numbered notes restart at 1. That is structurally identical
   to the Bible's table of contents (U-04), which once made Genesis's span two lines long. So
   a book's text ENDS at its own NOTES marker rather than at the next book heading.

Why this book is worth indexing at all: the ledger recorded Herodotus as having 「只有页锚点，
无正典地址」. That is exactly backwards — it has 763 canonical sections and ZERO page anchors,
while Darwin has 491 page anchors and no address finer than the chapter. Together they test
schema.sql's opening claim (D-005: 「both are needed and they are not interchangeable」) from
both directions, which no single book can do.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Line-initial only. A section marker inside a line is a cross-reference, never a section.
SECTION_RE = re.compile(r"(?m)^(\d{1,3})[.,]\s")
BOOK_RE = re.compile(r"(?m)^BOOK\s+([IVXLC]+)\.")
NOTES_RE = re.compile(r"(?m)^NOTES TO BOOK\s+([IVXLC]+)")

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman(s: str) -> int | None:
    total = prev = 0
    for ch in reversed(s.upper()):
        v = _ROMAN.get(ch)
        if v is None:
            return None
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total or None


@dataclass
class BookSpan:
    number: int
    label: str
    start: int          # raw offset of the heading
    text_end: int       # where the book's TEXT ends (its own NOTES marker, if any)


@dataclass
class Section:
    book: int
    number: int
    start: int
    end: int
    text: str


def book_spans(raw: str) -> list[BookSpan]:
    """Book headings, each bounded by its own NOTES block rather than by the next heading."""
    notes = [(m.start(), roman(m.group(1))) for m in NOTES_RE.finditer(raw)]
    books: list[tuple[int, int, str]] = []
    for m in BOOK_RE.finditer(raw):
        n = roman(m.group(1))
        if n:
            books.append((m.start(), n, m.group(0).strip()))

    out: list[BookSpan] = []
    for i, (pos, n, label) in enumerate(books):
        nxt = books[i + 1][0] if i + 1 < len(books) else len(raw)
        # This book's own NOTES marker, if it falls before the next book heading.
        own = [p for p, bn in notes if pos < p < nxt and (bn == n or bn is None)]
        end = min(own) if own else nxt
        out.append(BookSpan(n, label, pos, end))
    return out


def parse_sections(raw: str, min_ascending: bool = True) -> list[Section]:
    """Sections inside each book's TEXT region only.

    `min_ascending` drops any marker whose number does not continue the ascending run within
    its own book. Herodotus quotes numerals mid-narrative, and a quoted 「200,」 at line start
    is indistinguishable from a section marker by pattern alone — but not by ORDER.
    """
    out: list[Section] = []
    for span in book_spans(raw):
        region = raw[span.start:span.text_end]
        marks = [(m.start(), int(m.group(1)), m.end())
                 for m in SECTION_RE.finditer(region)]
        kept: list[tuple[int, int, int]] = []
        high = 0
        for pos, num, endpos in marks:
            if min_ascending and num <= high:
                continue
            kept.append((pos, num, endpos))
            high = num
        for k, (pos, num, endpos) in enumerate(kept):
            stop = kept[k + 1][0] if k + 1 < len(kept) else len(region)
            body = region[endpos:stop].strip()
            out.append(Section(span.number, num, span.start + pos,
                               span.start + stop, body))
    return out
