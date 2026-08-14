"""Douay-Rheims Bible parser — the third bcv-family edition.

The Douay-Rheims Old Testament (1582/1609-10, Challoner revision 1749-52) follows
Vulgate numbering and spelling, which differ from the Protestant KJV/WEB that
`bcv.parse_verses` already handles:

  Douay chapter heading : `Genesis Chapter 1`           (book short name + "Chapter N")
  Douay verse line      : `1:1. In the beginning ...`   (C:V. then space; 7 lines have no space)
  Douay book names      : Vulgate (Josue, Isaias, Osee, Micheas, Abdias, Aggeus, Zacharias,
                          Malachias, Habacuc, Sophonias, Jonas, Ezechiel, 1-4 Kings,
                          1-2 Paralipomenon, 1-2 Esdras, Tobias, Ecclesiasticus, 1-2 Machabees,
                          Canticle of Canticles, Apocalypse) — all 73 measured, mapped to the
                          bcv.BOOKS Protestant superset below.

`bcv.VERSE_RE = ^\s{0,6}(\d{1,3}):(\d{1,3})\s+(\S.*)$` does NOT match Douay: the required
`\s+` after group 2 cannot accept the `.` that follows the verse number in Douay
(`1:1.`). Measured before writing this module. `bcv.parse_verses` therefore returns
0 verses for Douay — this module is the separate path, mirroring how `bcv` is itself
a separate path from `zhouyi`.

Known Vulgate numbering anomalies (all measured from pg1581.txt):
  - Psalms 113: Vulgate merges Protestant Psalms 114+115 into one chapter, so the
    verse number resets 113:8 -> 113:1 mid-chapter. The second 113:1-8 is what KJV
    calls Psalms 115:1-9 (Latin numbering).
  - Proverbs 12:12 is printed twice with two different texts (one wine/glory, one
    wicked/just). This is a known Douay-verse duplication, not a parser bug.

We DO NOT silently deduplicate or renumber. Each verse line becomes one record;
duplicates surface as address collisions in `probe_bcv.py`, which is exactly where
U-08 taught us they must surface rather than be hidden by a comprehension dict.
"""
from __future__ import annotations

import re

from . import bcv
from .bcv import BOOK_INDEX

# "<BookShortName> Chapter <N>" — Douay chapter heading. Short name, no leading
# whitespace, plain digits (no Roman) — measured: 1334 headings, 73 distinct books.
DOUAY_CHAP_RE = re.compile(r"^(\S.+) Chapter (\d+)\s*$")

# Douay verse: `C:V.` then optional space then text. The 7 lines with no space
# after the dot (e.g. `19:18.They passed ...`) are covered by `\s*`.
DOUAY_VERSE_RE = re.compile(r"^(\d{1,3}):(\d{1,3})\.\s*(\S.*)$")

# Douay short book name -> bcv.BOOKS canonical (Protestant superset) name.
# Measured: 73 Douay short names map 1:1 to bcv.BOOKS's 73 entries. The Vulgate
# Kings/Paralipomenon/Esdras sequences are remapped to the Protestant order that
# bcv.BOOKS already encodes (the superset was added precisely to support Douay).
DOUAY_TO_BCV: dict[str, str] = {
    # identical names
    "Genesis": "Genesis", "Exodus": "Exodus", "Leviticus": "Leviticus",
    "Numbers": "Numbers", "Deuteronomy": "Deuteronomy", "Judges": "Judges",
    "Ruth": "Ruth", "Job": "Job", "Psalms": "Psalms", "Proverbs": "Proverbs",
    "Ecclesiastes": "Ecclesiastes", "Daniel": "Daniel", "Joel": "Joel",
    "Amos": "Amos", "Esther": "Esther", "Matthew": "Matthew", "Mark": "Mark",
    "Luke": "Luke", "John": "John", "Acts": "Acts", "Romans": "Romans",
    "James": "James", "Hebrews": "Hebrews",
    "1 Corinthians": "1 Corinthians", "2 Corinthians": "2 Corinthians",
    "Galatians": "Galatians", "Ephesians": "Ephesians",
    "Philippians": "Philippians", "Colossians": "Colossians",
    "1 Thessalonians": "1 Thessalonians", "2 Thessalonians": "2 Thessalonians",
    "1 Timothy": "1 Timothy", "2 Timothy": "2 Timothy",
    "Titus": "Titus", "Philemon": "Philemon",
    "1 Peter": "1 Peter", "2 Peter": "2 Peter",
    "1 John": "1 John", "2 John": "2 John", "3 John": "3 John", "Jude": "Jude",
    # Vulgate spelling -> Protestant canonical
    "Josue": "Joshua", "Isaias": "Isaiah", "Jeremias": "Jeremiah",
    "Ezechiel": "Ezekiel", "Osee": "Hosea", "Jonas": "Jonah",
    "Micheas": "Micah", "Nahum": "Nahum", "Habacuc": "Habakkuk",
    "Sophonias": "Zephaniah", "Aggeus": "Haggai", "Zacharias": "Zechariah",
    "Malachias": "Malachi", "Abdias": "Obadiah",
    "Canticle of Canticles": "Song of Solomon", "Apocalypse": "Revelation",
    # Vulgate Kings sequence: 1-4 Kings = 1-2 Samuel + 1-2 Kings (Protestant)
    "1 Kings": "1 Samuel", "2 Kings": "2 Samuel",
    "3 Kings": "1 Kings", "4 Kings": "2 Kings",
    # Vulgate Chronicles: Paralipomenon = Chronicles
    "1 Paralipomenon": "1 Chronicles", "2 Paralipomenon": "2 Chronicles",
    # Vulgate Esdras: 1 Esdras = Ezra, 2 Esdras = Nehemiah
    "1 Esdras": "Ezra", "2 Esdras": "Nehemiah",
    # Deuterocanonical (bcv.BOOKS already includes these)
    "Tobias": "Tobit", "Judith": "Judith", "Wisdom": "Wisdom",
    "Ecclesiasticus": "Sirach",
    "1 Machabees": "1 Maccabees", "2 Machabees": "2 Maccabees",
    "Lamentations": "Lamentations", "Baruch": "Baruch",
}


class Verse:
    """A single Douay verse record, addressable by (bcv_book, chapter, verse).

    `chapter` and `verse` come from the verse line's own `C:V` marker (not the
    chapter heading), because Psalms 113 resets the verse number mid-chapter and
    Proverbs 12:12 is printed twice — the verse line is the ground truth for
    which verse this is, while the chapter heading only names the book.
    """

    __slots__ = ("bcv_book", "chapter", "verse", "text", "raw_start", "raw_end")

    def __init__(self, bcv_book: str, chapter: int, verse: int,
                 text: str, raw_start: int, raw_end: int):
        self.bcv_book = bcv_book
        self.chapter = chapter
        self.verse = verse
        self.text = text
        self.raw_start = raw_start
        self.raw_end = raw_end


def parse_verses(text: str) -> list[Verse]:
    """Parse the full Douay-Rheims plain text into Verse records.

    Each verse spans from its `C:V.` marker to the next verse marker or chapter
    heading; continuation lines (wrapped text, summary lines, annotations) are
    accumulated into `text`.

    The verse's byte range (`raw_start`, `raw_end`) is computed against the SAME
    `text` string the caller passed in, so it is directly comparable to the
    `raw_start`/`raw_end` stored for every other unit in the index.
    """
    lines = text.splitlines(keepends=True)
    out: list[Verse] = []
    cur_bcv: str | None = None
    cur_chap: int | None = None
    cur_c: int | None = None
    cur_v: int | None = None
    buf_lines: list[str] = []
    buf_start: int = 0

    def flush(end_offset: int) -> None:
        nonlocal cur_c, cur_v, buf_lines, buf_start
        if cur_bcv is not None and cur_c is not None and buf_lines:
            joined = "".join(buf_lines).rstrip()
            out.append(Verse(cur_bcv, cur_c, cur_v,
                             joined, buf_start, buf_start + len(joined)))
        cur_c = cur_v = None
        buf_lines = []
        buf_start = end_offset

    offset = 0
    for line in lines:
        line_len = len(line)
        cm = DOUAY_CHAP_RE.match(line.rstrip("\r\n"))
        vm = DOUAY_VERSE_RE.match(line.rstrip("\r\n"))

        if cm:
            flush(offset)
            douay_name = cm.group(1)
            cur_bcv = DOUAY_TO_BCV.get(douay_name)
            cur_chap = int(cm.group(2))
        elif vm:
            flush(offset)
            cur_c, cur_v = int(vm.group(1)), int(vm.group(2))
            buf_lines = [vm.group(3)]
            buf_start = offset + line.index(vm.group(3))
        # Non-verse, non-chapter line: ignore (summary lines, annotations, TOC).
        # The TOC at lines 47-145 does NOT use "X Chapter N" form, so the chapter
        # regex naturally skips it.

        offset += line_len

    flush(offset)
    return out


def douay_to_bcv_index() -> dict[str, int]:
    """Return {douay_short_name: bcv canonical index} for the books that map."""
    return {d: BOOK_INDEX[b] for d, b in DOUAY_TO_BCV.items() if b in BOOK_INDEX}
