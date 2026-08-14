"""book/chapter/verse addressing — the second canonical scheme, proving D-016.

Written deliberately by REUSING the lessons D-006 paid for, because probe_generality.py
showed all three failure modes recur verbatim on this corpus:

1. Carry-forward misattribution. A throwaway "track the most recent book heading" parser
   answered Psalms 23:1 with Isaiah 23's text and John 3:16 with Revelation 3:16's. Same
   class of plausible-looking wrong answer as 周易 attempt 1. Fix is the same: the book
   sequence is FINITE and ORDERED, so take a longest strictly-increasing subsequence over
   canonical book indices and discard headings that do not fit the chain.

2. Cross-references mistaken for addresses. Douay-Rheims has 3 line-initial verse markers
   but 35,905 inline `C:V` tokens, which are marginal cross-references (`23:30 / 2 Par
   36:1`). Only line-initial markers are addresses — exactly as 十翼 citations of other
   hexagrams are not that hexagram's commentary.

3. Edition-specific markup. KJV writes `1:1 `, WEB writes `001:001 `, Douay puts verse
   numbers inline. One regex per edition family, discovered from the data.

Unknown stays unknown: a verse whose book cannot be placed on the chain gets None.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .anchors import _longest_increasing

# Protestant + Deuterocanonical superset in canonical order. Order is what matters; extra
# entries are harmless because LIS simply never selects them.
BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua", "Judges",
    "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles",
    "Ezra", "Nehemiah", "Tobit", "Judith", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Wisdom", "Sirach", "Isaiah", "Jeremiah",
    "Lamentations", "Baruch", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos", "Obadiah",
    "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "1 Maccabees", "2 Maccabees",
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians",
    "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians",
    "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon",
    "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude",
    "Revelation",
]
BOOK_INDEX = {b: i for i, b in enumerate(BOOKS)}

_ORD = {"first": "1", "second": "2", "third": "3", "i": "1", "ii": "2", "iii": "3"}
# Editions title books many ways: "The First Book of Moses: Called Genesis",
# "The Gospel According to Saint John", "The Book of Psalms", "THE FIRST EPISTLE OF PAUL
# THE APOSTLE TO THE CORINTHIANS". Rather than enumerate the templates, look for a known
# book name inside a short line, plus an ordinal if one is present.
_ORD_RE = re.compile(r"\b(first|second|third|i{1,3})\b", re.I)

# An ordinal can also be an ARABIC DIGIT sitting immediately before the book name, which is
# how WEB titles every numbered book: 「Book 12 2 Kings」, 「Book 62 1 John」.
#
# Missing this cost 10 of 66 books, and it did NOT fail loudly — it failed by returning
# another book's text under a well-formed citation, which is the worst failure this project
# has (GOAL §2). 「Book 12 2 Kings」 matched bare name "kings", found no ordinal WORD, and so
# fell through to `want = b[0]` = "1", yielding "1 Kings" — a name already on the LIS chain,
# so the duplicate was dropped and 2 Kings never got a span. Its verses then landed inside
# 1 Kings' span, and because probe_bcv builds {(book,chapter,verse): text} by comprehension,
# the later row WON: 1 Kings 1:1 returned 2 Kings' text. Measured before the fix
# (probes/probe_bcv_dupes.py): 31,102 rows collapsing to 29,214 addresses, all 1,865
# colliding addresses holding DIFFERENT text; 「Ruth 1:1」 returned 1 Samuel 1:1.
# 1/2/3 John were lost the same way via the unnumbered gospel "John".
#
# Deliberately restricted to a STANDALONE single digit 1-3 immediately preceding the name.
# A looser 「any digit before the name」 breaks unnumbered books: in 「Book 21 Ecclesiastes」
# the nearest digit is the "1" of "21", which would ask for a nonexistent "1 Ecclesiastes"
# and drop that heading instead.
_DIGIT_ORD_RE = re.compile(r"(?:^|\s)([123])\s+$")

# Line-initial verse marker only (finding 2 above). Zero-padding is allowed for WEB.
VERSE_RE = re.compile(r"^\s{0,6}(\d{1,3}):(\d{1,3})\s+(\S.*)$")
# Douay-style: chapter heading line, then verses numbered inline within the paragraph.
CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+([IVXLC\d]+)", re.I)
INLINE_VERSE_RE = re.compile(r"(?:^|\s)(\d{1,3})\.?\s+(?=[A-Z(])")
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman(s: str) -> int | None:
    s = s.upper()
    if s.isdigit():
        return int(s)
    if not s or any(c not in _ROMAN for c in s):
        return None
    total = prev = 0
    for c in reversed(s):
        v = _ROMAN[c]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total or None


# A book name occurring in a line does NOT make it a heading. Measured: a bare
# "does the line contain a known book name" test found 1,103 candidates for 66 books in KJV
# and 1,124 in WEB, because 「four kings against the five.」 contains "Kings" and
# 「The Old Testament of the King James Version」 contains "James". Require either a real
# heading template or that the name dominate the line.
_HEADING_TEMPLATES = [
    re.compile(r"^Book\s+\d+\s+\S", re.I),                       # WEB: "Book 01 Genesis"
    re.compile(r"^The\s+(First|Second|Third|Fourth|Fifth)?\s*Book\s+of\b", re.I),
    re.compile(r"^The\s+(Gospel|Acts|Revelation|Lamentations|Proverbs|Psalms|Song)\b", re.I),
    re.compile(r"^The\s+(First|Second|Third)?\s*(General\s+)?Epistle\b", re.I),
    re.compile(r"^The\s+\w+\s+of\s+(the\s+)?(Prophet|Apostle|Paul|Saint|St\.?)\b", re.I),
    re.compile(r"^(THE\s+)?[A-Z][A-Z\s.]{2,40}$"),                # all-caps heading line
]
_NAME_DOMINANCE = 0.40


def _looks_like_heading(s: str, bare: str) -> bool:
    # A prose sentence ending in a full stop is not a heading, however much of the line the
    # book name covers. Measured: 「came unto Jeremiah.」 and 「known to Daniel.」 both passed
    # the dominance test at 0.5 and were selected as book starts, which put Jeremiah's
    # chapter 23 inside the span labelled Isaiah — so Isaiah 23:1 returned Jeremiah 23:1.
    if s.endswith((".", ",", ";", ":", "!", "?", '"', "'")) and \
            not any(t.match(s) for t in _HEADING_TEMPLATES):
        return False
    if any(t.match(s) for t in _HEADING_TEMPLATES):
        return True
    letters = sum(1 for c in s if c.isalpha())
    return bool(letters) and len(bare) / letters >= _NAME_DOMINANCE


def book_in_line(line: str) -> str | None:
    """Canonical book name if this short line is plausibly its heading."""
    s = line.strip()
    if not s or len(s) > 72 or s[0].isdigit() and ":" in s[:6]:
        return None
    low = s.lower()
    ordinal = None
    m = _ORD_RE.search(low)
    if m:
        ordinal = _ORD.get(m.group(1).lower())
    best = None
    for b in BOOKS:
        bare = b.split(" ", 1)[1].lower() if b[0].isdigit() else b.lower()
        if re.search(rf"\b{re.escape(bare)}\b", low):
            # Prefer the longest matching bare name: "John" also matches "1 John".
            if best is None or len(bare) > len(best[0]):
                best = (bare, b)
    if not best:
        return None
    bare, b = best
    if not _looks_like_heading(s, bare):
        return None

    # A digit ordinal immediately before the matched name outranks an ordinal WORD elsewhere
    # in the line: it is adjacent to the name it qualifies, whereas a word can belong to
    # something else entirely (「THE FIRST BOOK OF THE KINGS」 vs 「Book 12 2 Kings」).
    at = low.rfind(bare)
    dm = _DIGIT_ORD_RE.search(low[:at]) if at > 0 else None
    if dm:
        ordinal = dm.group(1)

    if b[0].isdigit():
        want = ordinal or b[0]
        cand = f"{want} {b.split(' ', 1)[1]}"
        return cand if cand in BOOK_INDEX else None
    # An unnumbered book name preceded by an ordinal belongs to the numbered variant.
    if ordinal and f"{ordinal} {b}" in BOOK_INDEX:
        return f"{ordinal} {b}"
    return b


@dataclass
class BookSpan:
    name: str
    index: int
    start_line: int
    end_line: int


def book_spans(lines: list[str]) -> list[BookSpan]:
    """Segment by book using LIS over canonical indices, not carry-forward.

    Carry-forward is what produced Isaiah's text for Psalms 23:1: every table-of-contents
    entry, running header and cross-reference reset the current book. LIS keeps only a
    strictly increasing chain, so those are dropped without special-casing any of them.

    A second filter is needed before LIS, and it is not optional: a Gutenberg Bible lists
    every book in a table of contents AND again at the book itself, so there are TWO
    canonically-ordered chains and LIS happily selects a mixture of them. Measured in KJV:
    the TOC occupies lines 2..10, so `Genesis` came out as the span lines 2..3 and 21 of 68
    spans contained no verse at all, which is why John 3:16 returned Romans 3:16.

    The discriminator is in the data: a real book heading is followed within a few lines by
    a verse marker; a TOC entry is not. 周易 never needed this because Kanripo files have no
    table of contents — a reminder that "it worked on the first corpus" is not evidence of
    generality.
    """
    def has_verse_soon(i: int, reach: int = 12) -> bool:
        return any(VERSE_RE.match(lines[j])
                   for j in range(i + 1, min(i + reach, len(lines))))

    marks: list[tuple[int, str, int]] = []
    for i, line in enumerate(lines):
        b = book_in_line(line)
        if b is not None and has_verse_soon(i):
            marks.append((i, b, BOOK_INDEX[b]))
    if not marks:
        return []
    keep = set(_longest_increasing([idx for _, _, idx in marks]))
    chain = [marks[k] for k in sorted(keep)]
    out = []
    for n, (ln, name, idx) in enumerate(chain):
        end = chain[n + 1][0] if n + 1 < len(chain) else len(lines)
        out.append(BookSpan(name, idx, ln, end))
    return out


def parse_verses(text: str) -> list[tuple[str, int, int, str]]:
    """-> [(book, chapter, verse, text)]. Only line-initial markers count as addresses."""
    lines = text.splitlines()
    spans = book_spans(lines)
    out: list[tuple[str, int, int, str]] = []
    for sp in spans:
        chapter = None
        pending: tuple[int, int] | None = None
        buf: list[str] = []
        for line in lines[sp.start_line:sp.end_line]:
            m = VERSE_RE.match(line)
            if m:
                if pending:
                    out.append((sp.name, pending[0], pending[1], " ".join(buf).strip()))
                pending, buf = (int(m.group(1)), int(m.group(2))), [m.group(3)]
                continue
            cm = CHAPTER_RE.match(line)
            if cm:
                if pending:
                    out.append((sp.name, pending[0], pending[1], " ".join(buf).strip()))
                    pending, buf = None, []
                chapter = roman(cm.group(1))
                continue
            if pending:
                if line.strip():
                    buf.append(line.strip())
                else:
                    out.append((sp.name, pending[0], pending[1], " ".join(buf).strip()))
                    pending, buf = None, []
        if pending:
            out.append((sp.name, pending[0], pending[1], " ".join(buf).strip()))
        del chapter
    return out
