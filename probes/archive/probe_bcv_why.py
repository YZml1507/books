"""Why does the bcv book chain misplace verses? Hypothesis: TWO ordered chains.

A Gutenberg Bible lists every book in a table of contents AND again at the book itself.
Both sequences are canonically ordered, so LIS can select a mixture of the two — a span
that starts at a TOC line and ends at a body line contains no verses at all, while the next
span inherits the previous book's text. That would explain spans=68 but only 47 books with
verses, and John 3:16 returning Romans 3:16.

周易 never showed this because Kanripo files carry no table of contents. If confirmed, the
discriminator is available in the data: a REAL book heading is followed within a few lines
by a verse marker; a TOC entry is not.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.bcv import VERSE_RE, book_in_line, book_spans  # noqa: E402

EXT = os.path.join(ROOT, "data", "raw_ext", "generality")
IDS = {"bible-kjv": 10, "bible-web": 8294, "bible-douay": 1581}

for slug, gid in IDS.items():
    raw = open(os.path.join(EXT, slug, f"pg{gid}.txt"),
               encoding="utf-8", errors="replace").read()
    lines = raw.splitlines()
    marks = [(i, b) for i, l in enumerate(lines) if (b := book_in_line(l))]
    print(f"\n{'='*76}\n{slug}: {len(marks)} heading-like lines, {len(lines):,} lines")

    # how many times does each book name appear as a heading?
    from collections import Counter
    c = Counter(b for _, b in marks)
    multi = {b: n for b, n in c.items() if n > 1}
    print(f"  books appearing more than once: {len(multi)}  "
          f"e.g. {list(multi.items())[:5]}")

    # is each heading followed by a verse marker soon after?
    def followed(i, reach=12):
        return any(VERSE_RE.match(lines[j]) for j in range(i + 1, min(i + reach, len(lines))))

    with_v = [(i, b) for i, b in marks if followed(i)]
    print(f"  headings followed by a verse marker within 12 lines: "
          f"{len(with_v)} / {len(marks)}")

    print("  first 8 Genesis/Exodus-ish marks (line, book, followed?):")
    for i, b in marks[:10]:
        print(f"    {i:7} {b:16} followed={followed(i)}   {lines[i].strip()[:52]}")

    # what did the current chain actually select?
    spans = book_spans(lines)
    empty = [s for s in spans
             if not any(VERSE_RE.match(lines[j]) for j in range(s.start_line, s.end_line))]
    print(f"  current chain: {len(spans)} spans, {len(empty)} contain NO verse markers")
    if empty:
        print(f"    empty spans: {[(s.name, s.start_line, s.end_line) for s in empty[:6]]}")
    print(f"  span for John: "
          f"{[(s.name, s.start_line, s.end_line) for s in spans if s.name == 'John']}")
    # where do John's verses actually live?
    j = [i for i, b in with_v if b == "John"]
    print(f"  'John' headings followed by verses at lines: {j}")
