"""Does the bcv parser actually place verses correctly across three translations?

Control cases are chosen because the earlier naive parser got them demonstrably WRONG:
  Psalms 23:1  -> it returned Isaiah 23's text
  John 3:16    -> it returned Revelation 3:16's text
A parser that passes these has fixed the carry-forward defect, not merely moved it.
"""
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.bcv import book_spans, parse_verses  # noqa: E402

EXT = os.path.join(ROOT, "data", "raw_ext", "generality")
IDS = {"bible-kjv": 10, "bible-web": 8294, "bible-douay": 1581}

# Needles must be wording-neutral. "only begotten" was a KJV-ism and marked WEB as BAD when
# WEB's correct text reads "one and only Son" — the test was wrong, not the parser. Picking a
# needle that survives translation is the whole point of a canonical address.
EXPECT = {
    ("Psalms", 23, 1): ("shepherd",),
    ("John", 3, 16): ("loved the world",),
    ("Genesis", 1, 1): ("beginning",),
    ("Revelation", 3, 16): ("lukewarm",),
    ("Isaiah", 23, 1): ("Tarshish",),
}

parsed = {}
raws: dict[str, list] = {}
for slug, gid in IDS.items():
    raw = open(os.path.join(EXT, slug, f"pg{gid}.txt"),
               encoding="utf-8", errors="replace").read()
    lines = raw.splitlines()
    spans = book_spans(lines)
    vs = parse_verses(raw)
    raws[slug] = vs                      # keep the ROWS, not just the deduped dict
    parsed[slug] = {(b, c, v): t for b, c, v, t in vs}
    books = Counter(b for b, _, _, _ in vs)
    print(f"{slug:14} {len(spans):3} book spans, {len(vs):>7,} verses, "
          f"{len(books):3} books with verses")
    chain = " ".join(s.name for s in spans[:6])
    print(f"               chain starts: {chain}")

print(f"\n=== control cases (the naive parser answered the first two WRONG) ===")
fails = []
SUPPORTED = ("bible-kjv", "bible-web")   # Douay numbers verses inline; not yet parsed
for (book, ch, v), needles in EXPECT.items():
    print(f"\n  {book} {ch}:{v}   expect to contain one of {needles}")
    for slug in IDS:
        t = parsed[slug].get((book, ch, v))
        if t is None:
            print(f"    {slug:14} (not located)")
            if slug in SUPPORTED:
                fails.append((slug, book, ch, v, "not located"))
            continue
        ok = any(n.lower() in t.lower() for n in needles)
        print(f"    {slug:14} [{'OK ' if ok else 'BAD'}] {t[:78]}")
        if not ok and slug in SUPPORTED:
            fails.append((slug, book, ch, v, "wrong text"))

print("\n=== cross-translation comparison at one address (the tier-1 capability) ===")
for key in (("John", 3, 16), ("Psalms", 23, 1)):
    print(f"\n  {key[0]} {key[1]}:{key[2]}")
    for slug in IDS:
        t = parsed[slug].get(key)
        if t:
            print(f"    {slug:14} {t[:100]}")

print(f"\n=== book coverage: how many of the 66/73 books got verses? ===")
for slug in IDS:
    got = {b for b, _, _ in parsed[slug]}
    print(f"  {slug:14} {len(got):3} books, "
          f"{len(parsed[slug]):>7,} verses")

print("\n=== CONTROL: no address may hold two different texts ===")
# This gate used to print two different verse totals for bible-web in one run — 31,102 rows
# but 29,214 dict keys — and nobody reconciled them. The gap was 10 undetected book headings
# ("Book 12 2 Kings" carries an ARABIC ordinal, which book_in_line ignored), so each missing
# book's verses were filed under the PRECEDING book and, the dict keeping the last writer,
# 「Ruth 1:1」 returned 1 Samuel 1:1. Every one of the 5 control cases passed throughout,
# because they test books whose spans happened to be right.
#
# Asserting rows == distinct keys is what makes that class of defect impossible to ship
# quietly: a collapsed address means two passages claim one citation.
for slug in IDS:
    vs = raws.get(slug)
    if vs is None:
        continue
    keys = Counter((b, c, v) for b, c, v, _ in vs)
    dup = {k: n for k, n in keys.items() if n > 1}
    conflict = 0
    if dup:
        seen: dict[tuple, set] = {}
        for b, ch, v, t in vs:
            if (b, ch, v) in dup:
                seen.setdefault((b, ch, v), set()).add(t)
        conflict = sum(1 for ts in seen.values() if len(ts) > 1)
    ok = conflict == 0
    print(f"  [{'PASS' if ok else 'FAIL'}] {slug:14} rows={len(vs):,} "
          f"distinct={len(keys):,} addresses holding conflicting text={conflict}")
    if not ok:
        fails.append(f"{slug}:{conflict} conflicting addresses")

print("\n=== CONTROL: both full Bibles must reach all 66 books ===")
for slug in ("bible-kjv", "bible-web"):
    got = {b for b, _, _ in parsed.get(slug, {})}
    ok = len(got) == 66
    print(f"  [{'PASS' if ok else 'FAIL'}] {slug:14} {len(got)}/66 books")
    if not ok:
        fails.append(f"{slug}:{len(got)}/66 books")

print(f"\n{'FAILURES: ' + str(fails) if fails else 'control cases PASS'}")
# Exit status, so this can be used as a gate rather than read by eye. It was already listed
# as one of the eight red-line commands while always exiting 0 — including on the run that
# printed 56/66 books and two different verse totals.
sys.exit(1 if fails else 0)
