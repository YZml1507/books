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


def _strip_tags(html: str) -> tuple[str, list[int]]:
    """Strip HTML tags, preserve text content. Handles entities.

    CRITICAL: small-caps spans must be removed with the EMPTY string, not a
    space. The html wraps each letter of a small-caps word in its own
    `<span class="small-caps">X</span>` (6,972 such single-char spans measured),
    so a naive `<[^>]+>` → ' ' replacement turns 'Problem' into 'P r o b l e m'.
    Removing the small-caps span tags (but keeping their letter content) lets
    the letters rejoin into a word.

    Returns (stripped_text, html_offsets) where html_offsets[i] is the html
    offset of the character stripped_text[i]. This lets callers map stripped
    offsets back to html offsets, so unit.raw_start/raw_end can point into the
    html file and unit.text can be the stripped (readable) version of that span.
    """
    # Walk the ORIGINAL html (not a pre-substituted copy), so html_offsets are
    # offsets into the original html. Recognise small-caps spans explicitly and
    # keep their inner letter; strip every other tag with a space; drop entities.
    SMALL_CAPS_OPEN = '<span class="small-caps">'
    out_chars: list[str] = []
    out_html: list[int] = []
    i = 0
    n = len(html)
    while i < n:
        ch = html[i]
        # Small-caps span: <span class="small-caps">X</span> -> keep X (the letter)
        if html.startswith(SMALL_CAPS_OPEN, i):
            inner_start = i + len(SMALL_CAPS_OPEN)
            close = html.find('</span>', inner_start)
            if close != -1:
                inner = html[inner_start:close]
                for off, c in enumerate(inner):
                    out_chars.append(c)
                    out_html.append(inner_start + off)
                i = close + len('</span>')
                continue
        if ch == '<':
            j = html.find('>', i)
            if j == -1:
                # malformed: treat literally
                out_chars.append(ch)
                out_html.append(i)
                i += 1
                continue
            i = j + 1
            continue
        if ch == '&':
            j = html.find(';', i)
            if j != -1 and j - i <= 12:
                i = j + 1
                continue
        out_chars.append(ch)
        out_html.append(i)
        i += 1
    stripped = ''.join(out_chars)
    # Collapse \s+ on the stripped text, keeping the html offset of the FIRST
    # surviving character of each run. This preserves 1:1 mapping between
    # collapsed-stripped chars and html offsets.
    collapsed_chars: list[str] = []
    collapsed_html: list[int] = []
    prev_ws = False
    for idx, ch in enumerate(stripped):
        if ch.isspace():
            if prev_ws:
                continue
            prev_ws = True
            collapsed_chars.append(' ')
            collapsed_html.append(out_html[idx])
        else:
            prev_ws = False
            collapsed_chars.append(ch)
            collapsed_html.append(out_html[idx])
    # Drop leading whitespace
    while collapsed_chars and collapsed_chars[0].isspace():
        collapsed_chars.pop(0)
        collapsed_html.pop(0)
    result = ''.join(collapsed_chars)
    return result, collapsed_html


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
    roman (roman numeral string), start/end offsets in the STRIPPED text, and
    text (the stripped, readable version of that span).

    The stripped-text space is what raw_body() returns for euclid-elements
    (see evalset.raw_body), so unit.raw_start/raw_end and raw_body() agree —
    the same invariant every other scheme has. The html_offsets returned by
    _strip_tags are not used here; they exist for callers that need to map
    back to the html source.
    """
    text, _html_offsets = _strip_tags(html)
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
            rom = _int_to_roman(num)
            prop_start = h.start()
            # End: next proposition heading, or end of book region
            if i + 1 < len(sorted_nums):
                prop_end = seen_nums[sorted_nums[i + 1]].start()
            else:
                prop_end = len(region)
            prop_text = region[prop_start:prop_end].strip()
            # Stripped-text offsets (same space as raw_body for euclid).
            s = book_start + prop_start
            e = book_start + prop_end
            props.append(Proposition(
                book=book_num,
                number=num,
                roman=rom,
                start=s,
                end=e,
                text=prop_text,
            ))

    return props
