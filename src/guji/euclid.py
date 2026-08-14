"""`euclid` — book/proposition addressing, for Euclid's Elements (Books I-VI).

Source: data/raw_ext/generality/euclid-elements/pg21076.html (1.83M chars, no .txt).
Stripped-of-tags text is 511,631 chars.

Measured structure (probes/probe_euclid_deep.py):
    BOOK I..VI headings: 6  (each appears once as 'BOOK n')
    PROP. <roman>: 202 total, distributed:
        I-VII: 8 each   VIII-XIV: 7 each   XV-XXI: 5-6   XXII-XXXIV: 2-4   XXXV-XLVIII: 1-2
    D[EÉ]FINITION: 67   Cor. (corollary): 154

The 202 PROP. markers include each proposition's heading PLUS its in-text
references ('by Prop. III. 16' etc). We cannot count propositions by
matching 'PROP. n' alone — that double-counts cross-references.

Canonical counts (Euclid Elements I-VI):
    Book I: 48 propositions
    Book II: 14
    Book III: 37
    Book IV: 16
    Book V: 25
    Book VI: 33
    Total: 173 propositions

Strategy:
  1. Find the 6 BOOK heading positions (boundaries between books).
  2. Within each book, find DEFINITION blocks (optional) and PROPOSITION blocks.
     A proposition block starts at a heading like 'PROPOSITION n' (spelled out)
     and runs until the next proposition or the book's end.
  3. addr1 = book number (1-6), addr2 = proposition roman numeral.

Key challenge: propositions are headed 'PROPOSITION n' (spelled out) in the
stripped text, but my probe found 0 of those. Re-checking: the html likely uses
'<h3>PROPOSITION 1</h3>' or similar, and stripping tags leaves 'PROPOSITION 1'.
The probe searched for 'PROPOSITION\s+([IVXLC]+)' (roman) — but the numerals
might be ARABIC (1, 2, 3...) not roman. Let me check both.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Proposition:
    book: int               # 1-6
    number: int             # arabic proposition number within the book
    roman: str              # roman numeral form (for display)
    start: int              # raw offset in stripped text
    end: int
    text: str


def _strip_tags(html: str) -> str:
    """Strip HTML tags, preserve text content. Handles entities.

    CRITICAL: small-caps spans must be removed with the EMPTY string, not a
    space. The html wraps each letter of a small-caps word in its own
    `<span class="small-caps">X</span>` (6,972 such single-char spans measured),
    so a naive `<[^>]+>` → ' ' replacement turns 'Problem' into 'P r o b l e m'.
    Removing the small-caps span tags (but keeping their letter content) lets
    the letters rejoin into a word.
    """
    # First, neutralise small-caps spans: drop the tags, keep the inner letter.
    t = re.sub(r'<span class="small-caps">([^<]*)</span>', r'\1', html)
    # Then strip all remaining tags with a space (block-level boundaries).
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&[a-zA-Z#0-9]+;", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _roman_to_int(s: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = prev = 0
    for ch in reversed(s.upper()):
        v = values.get(ch, 0)
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total


def _int_to_roman(n: int) -> str:
    table = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
             (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    out = ""
    for v, s in table:
        while n >= v:
            out += s
            n -= v
    return out


_BOOK_RE = re.compile(r"(?:^|\s)BOOK\s+([IVX]+)[\.\s]", re.M)
# Proposition headings: 'PROPOSITION 1' or 'PROPOSITION I' or 'PROP. 1'
_PROP_HEAD_RE = re.compile(
    r"(?:PROPOSITION|PROP\.?)\s+([IVXLC]+|\d+)[\.\s]", re.I)


def find_books(text: str) -> list[tuple[int, int, int]]:
    """Return list of (book_number, start, end) for the 6 books (I-VI).

    Euclid's Elements (this edition) covers only Books I-VI. A stray
    'BOOK XI' in the front matter (a translator's note referencing Euclid
    Book XI, which is not in this edition) would otherwise create a
    phantom Book 11. We hard-filter to 1..6.
    """
    matches = list(_BOOK_RE.finditer(text))
    # Deduplicate: keep first occurrence of each roman numeral
    seen = {}
    for m in matches:
        rom = m.group(1)
        if rom not in seen:
            seen[rom] = m
    # Sort by position
    books = sorted(seen.items(), key=lambda x: x[1].start())
    out = []
    for i, (rom, m) in enumerate(books):
        n = _roman_to_int(rom)
        if not (1 <= n <= 6):
            continue
        start = m.start()
        end = books[i + 1][1].start() if i + 1 < len(books) else len(text)
        out.append((n, start, end))
    return out


def parse_propositions(html: str) -> list[Proposition]:
    """Parse Euclid's Elements html into propositions.

    Returns a list of Proposition objects with book (1-6), number (arabic),
    roman (roman numeral string), start/end offsets in stripped text, and text.
    """
    text = _strip_tags(html)
    books = find_books(text)

    props = []
    for book_num, book_start, book_end in books:
        region = text[book_start:book_end]
        # Find all proposition headings in this book's region
        heads = list(_PROP_HEAD_RE.finditer(region))
        # Filter: a real heading is followed by text (the proposition statement)
        # and is typically near the start of a line in the original. Since we
        # stripped to a single line, we rely on context.
        # Deduplicate by number: keep first occurrence of each proposition number.
        seen_nums = {}
        for h in heads:
            raw = h.group(1)
            if raw.isdigit():
                num = int(raw)
                rom = _int_to_roman(num)
            else:
                num = _roman_to_int(raw)
                rom = raw
            if num in seen_nums:
                continue
            seen_nums[num] = h

        # Sort propositions by number
        sorted_nums = sorted(seen_nums.keys())
        for i, num in enumerate(sorted_nums):
            h = seen_nums[num]
            rom = _int_to_roman(num) if not h.group(1).isdigit() and not h.group(1).isalpha() else (h.group(1) if h.group(1).isalpha() else _int_to_roman(num))
            # Simplify: use the roman form we computed
            rom = _int_to_roman(num)
            prop_start = h.start()
            # End: next proposition heading, or end of book region
            if i + 1 < len(sorted_nums):
                prop_end = seen_nums[sorted_nums[i + 1]].start()
            else:
                prop_end = len(region)
            prop_text = region[prop_start:prop_end].strip()
            props.append(Proposition(
                book=book_num,
                number=num,
                roman=rom,
                start=book_start + prop_start,
                end=book_start + prop_end,
                text=prop_text,
            ))

    return props
