"""Test: can booksec.py parse Homer Iliad (Butler and Pope)?

Both translations have 24 BOOK headings (I-XXIV).
"""
import sys
sys.path.insert(0, "src")
from guji import booksec
from pathlib import Path

for slug, fname in [("homer-iliad-but", "pg2199.txt"),
                    ("homer-iliad-pope", "pg6130.txt")]:
    raw = (Path("data/raw_ext/generality") / slug / fname).read_text(encoding="utf-8", errors="replace")
    spans = booksec.book_spans(raw)
    print(f"\n=== {slug} ===")
    print(f"booksec.book_spans found: {len(spans)} books")
    for s in spans[:5]:
        print(f"  BOOK {s.number}  start={s.start}  text_end={s.text_end}  label={s.label!r}")
    if len(spans) > 5:
        print(f"  ... {len(spans)-5} more")
    nums = sorted(set(s.number for s in spans))
    print(f"  distinct book numbers: {nums}")
    print(f"  range: {nums[0]}..{nums[-1]}" if nums else "  EMPTY")
    # Check NOTES markers
    notes = list(booksec.NOTES_RE.finditer(raw))
    print(f"  NOTES markers: {len(notes)}")
