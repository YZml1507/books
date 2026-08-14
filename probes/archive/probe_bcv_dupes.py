"""P-02: probe_bcv.py prints 31,102 verses and then 29,214 verses for bible-web in ONE run.

Both numbers are printed by the same script from the same parse:
    len(vs)            -> 31,102     the rows parse_verses returned
    len(parsed[slug])  -> 29,214     those rows put in a dict keyed by (book, chapter, verse)

So 1,888 rows share a key with an earlier row and are silently overwritten. A gate that
reports two different totals for the same quantity cannot be trusted to report anything, and
the important question is which of the two is right — i.e. are the duplicate keys

  (a) a PARSER DEFECT: the same verse emitted twice, or a verse assigned to the wrong book
      because a book span was mis-bounded (the failure mode U-04/U-05 already found twice), or
  (b) LEGITIMATE: the translation genuinely prints two blocks that map to one address
      (front matter, a duplicated psalm, translator's footnotes).

The distinction matters beyond tidiness: if (a), then the 5/5 control cases pass while the
parser is quietly misplacing 6% of verses, which is exactly the shape of the 有能乾○九乾
failure — every count-based check green, the text wrong.

Read-only. Touches no shared state.
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.bcv import book_spans, parse_verses  # noqa: E402

EXT = os.path.join(ROOT, "data", "raw_ext", "generality")
IDS = {"bible-kjv": 10, "bible-web": 8294, "bible-douay": 1581}


def load(slug: str, gid: int) -> str:
    for name in (f"{slug}.txt", f"pg{gid}.txt", f"{gid}.txt"):
        p = os.path.join(EXT, slug, name)
        if os.path.exists(p):
            return open(p, encoding="utf-8", errors="replace").read()
    d = os.path.join(EXT, slug)
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".txt"):
                return open(os.path.join(d, f), encoding="utf-8",
                            errors="replace").read()
    return ""


for slug, gid in IDS.items():
    raw = load(slug, gid)
    if not raw:
        print(f"\n{slug}: no text on disk")
        continue
    vs = parse_verses(raw)
    spans = book_spans(raw.splitlines())
    keys = Counter((b, c, v) for b, c, v, _ in vs)
    dupes = {k: n for k, n in keys.items() if n > 1}
    print(f"\n{'=' * 78}\n{slug}: rows={len(vs):,}  distinct keys={len(keys):,}  "
          f"lost to overwrite={len(vs) - len(keys):,}")
    print(f"  keys appearing more than once: {len(dupes):,}")
    if not dupes:
        continue

    # Are the duplicate rows identical text (harmless) or different text (a real conflict)?
    texts = defaultdict(list)
    for b, c, v, t in vs:
        if (b, c, v) in dupes:
            texts[(b, c, v)].append(t)
    same = sum(1 for k, ts in texts.items() if len(set(ts)) == 1)
    diff = len(texts) - same
    print(f"  of those, identical text: {same:,}   DIFFERENT text: {diff:,}")

    by_book = Counter(k[0] for k in dupes)
    print(f"  duplicate keys concentrated in: {by_book.most_common(8)}")

    print("\n  --- sample conflicts (different text under one address) ---")
    shown = 0
    for k, ts in texts.items():
        if len(set(ts)) > 1 and shown < 6:
            shown += 1
            print(f"\n  {k[0]} {k[1]}:{k[2]}  ({len(ts)} rows)")
            for t in ts[:3]:
                print(f"      {t[:110]!r}")

    # Does a duplicated key sit inside more than one book span? That would mean a span
    # boundary is wrong, which is the U-04/U-05 failure mode rather than a benign repeat.
    names = [s.name for s in spans]
    print(f"\n  book spans: {len(spans)}   duplicated span names: "
          f"{[n for n, c in Counter(names).items() if c > 1]}")
