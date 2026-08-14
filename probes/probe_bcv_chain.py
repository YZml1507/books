"""Isaiah 23:1 returns Jeremiah 23:1 in BOTH editions. A consistent wrong answer means the
chain's LABELS are shifted relative to its spans, not that a verse is missing.

66 spans and 66 books with verses looks correct, so the count check is not sufficient — this
is exactly the kind of defect that a coverage number hides (same lesson as D-012). Compare
the selected chain against the canonical order position by position.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.bcv import BOOKS, VERSE_RE, book_in_line, book_spans  # noqa: E402

EXT = os.path.join(ROOT, "data", "raw_ext", "generality")
IDS = {"bible-kjv": 10, "bible-web": 8294}

for slug, gid in IDS.items():
    raw = open(os.path.join(EXT, slug, f"pg{gid}.txt"),
               encoding="utf-8", errors="replace").read()
    lines = raw.splitlines()
    spans = book_spans(lines)
    print(f"\n{'='*74}\n{slug}: {len(spans)} spans")
    got = [s.name for s in spans]
    dupes = [b for b in got if got.count(b) > 1]
    print(f"  duplicated labels: {sorted(set(dupes))}")
    missing = [b for b in BOOKS if b not in got]
    print(f"  canonical books absent from chain: {len(missing)}")

    # For each span, does its FIRST verse text look like it belongs to the labelled book?
    # Use the heading line itself as ground truth: print label vs the actual heading text.
    print(f"\n  {'label':18} {'heading line as printed':52}")
    for s in spans:
        head = lines[s.start_line].strip()[:50]
        flag = "" if s.name.split()[-1].lower() in head.lower() else "  <-- MISMATCH"
        if flag or s.name in ("Isaiah", "Jeremiah", "Ecclesiastes", "Song of Solomon",
                              "Lamentations", "Ezekiel", "Daniel"):
            print(f"  {s.name:18} {head:52}{flag}")

    # Where is Isaiah's real heading?
    print("\n  lines mentioning Isaiah as a heading candidate:")
    for i, l in enumerate(lines):
        if "isaiah" in l.lower() and len(l.strip()) < 72:
            b = book_in_line(l)
            v = any(VERSE_RE.match(lines[j]) for j in range(i + 1, min(i + 12, len(lines))))
            print(f"    {i:7} detected={b!s:14} verse_soon={v!s:5} {l.strip()[:52]}")
        if i > 40000:
            break
