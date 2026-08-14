"""Which books does the bcv parser MISS in bible-web, and what does that do to addresses?

Established by probes/probe_bcv_dupes.py: bible-web parses 31,102 verse rows into only
29,214 distinct addresses, and all 1,865 colliding addresses hold DIFFERENT text. The
sample was unambiguous — the second row under `Ruth 1:1` is

    'Now there was a certain man of Ramathaim Zophim ... and his name was Elkanah'

which is 1 Samuel 1:1. So a book whose heading is not detected has its verses filed under
the PRECEDING book's addresses, and because probe_bcv builds `{(b,c,v): text}` by
comprehension, the LAST row wins — the real Ruth 1:1 is not merely duplicated, it is
REPLACED by 1 Samuel's text.

That makes this the project's most serious failure class, not a coverage gap: ask for one
address, get another book's text, with a citation that looks perfectly well-formed. And the
existing 5/5 control cases all pass, because they test books whose spans happen to be right
(Genesis, Psalms, Isaiah, John, Revelation).

This probe answers: WHICH books are missing, and WHY the heading was not recognised.
The canonical list is taken from bible-kjv, which parses all 66 with zero collisions — an
internal witness, not a hardcoded list.

Read-only.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.bcv import book_spans, parse_verses  # noqa: E402

EXT = os.path.join(ROOT, "data", "raw_ext", "generality")


def load(slug: str) -> str:
    d = os.path.join(EXT, slug)
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".txt"):
                return open(os.path.join(d, f), encoding="utf-8",
                            errors="replace").read()
    return ""


kjv, web = load("bible-kjv"), load("bible-web")
k_spans = [s.name for s in book_spans(kjv.splitlines())]
w_spans = [s.name for s in book_spans(web.splitlines())]
print(f"kjv spans {len(k_spans)}   web spans {len(w_spans)}")

missing = [b for b in k_spans if b not in w_spans]
extra = [b for b in w_spans if b not in k_spans]
print(f"\n=== books in KJV's chain but NOT in WEB's ({len(missing)}) ===")
for b in missing:
    print(f"  {b}")
if extra:
    print(f"\n=== in WEB's chain but not KJV's ({len(extra)}) ===  {extra}")

print("\n=== where the collisions land (from probe_bcv_dupes) ===")
vs = parse_verses(web)
keys = Counter((b, c, v) for b, c, v, _ in vs)
dupes = Counter(k[0] for k, n in keys.items() if n > 1)
print("  book absorbing foreign verses -> count of colliding addresses")
for b, n in dupes.most_common(14):
    nxt = k_spans[k_spans.index(b) + 1] if b in k_spans and \
        k_spans.index(b) + 1 < len(k_spans) else "?"
    flag = "  <- next book in canon is MISSING" if nxt in missing else ""
    print(f"    {b:18s} {n:5d}   (next in canon: {nxt}){flag}")

print("\n=== how does WEB actually print the missing books' headings? ===")
lines = web.splitlines()
for b in missing[:8]:
    # Find any line that mentions the book name, and show it with its neighbours, so the
    # real printed form is visible rather than assumed.
    hits = [i for i, ln in enumerate(lines)
            if re.search(re.escape(b), ln, re.I)]
    print(f"\n  --- {b}: {len(hits)} lines mention it ---")
    for i in hits[:4]:
        ctx = []
        for j in range(max(0, i - 2), min(len(lines), i + 3)):
            mark = ">>" if j == i else "  "
            ctx.append(f"      {mark} L{j}: {lines[j][:96]!r}")
        print("\n".join(ctx))
        print()

print("\n=== what does WEB print for a book that WAS found, for comparison? ===")
for b in ("Ruth", "Psalms"):
    if b not in w_spans:
        continue
    s = [x for x in book_spans(lines) if x.name == b][0]
    print(f"\n  {b}: span starts at line {s.start}")
    for j in range(max(0, s.start - 3), min(len(lines), s.start + 4)):
        mark = ">>" if j == s.start else "  "
        print(f"      {mark} L{j}: {lines[j][:96]!r}")
