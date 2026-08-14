"""Test: can booksec.py parse Plato Republic directly?

Plato has 10 BOOK headings (I-X), same 'BOOK n' own-line format as Herodotus.
If booksec.book_spans works, Plato is a ONE-LINE addition to ingest.py
(scheme='booksec'), not a new parser.
"""
import sys
sys.path.insert(0, "src")
from guji import booksec
from pathlib import Path

raw = (Path("data/raw_ext/generality") / "plato-republic" / "pg1497.txt").read_text(encoding="utf-8", errors="replace")

spans = booksec.book_spans(raw)
print(f"booksec.book_spans found: {len(spans)} books")
for s in spans:
    print(f"  BOOK {s.number}  start={s.start}  text_end={s.text_end}  label={s.label!r}")

# Also test parse_sections — does it find sections within each book?
sections = booksec.parse_sections(raw)
print(f"\nbooksec.parse_sections found: {len(sections)} sections")
if sections:
    print(f"  first section: book={sections[0].book} num={sections[0].number} text={sections[0].text[:60]!r}")
    print(f"  last section:  book={sections[-1].book} num={sections[-1].number} text={sections[-1].text[:60]!r}")

# Count sections per book
from collections import Counter
pc = Counter(s.book for s in sections)
for bk in sorted(pc):
    print(f"  BOOK {bk}: {pc[bk]} sections")
