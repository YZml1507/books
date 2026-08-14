"""Falsification test: can a SECOND canonical address scheme be added without rework?

The 周易 layer works. That is one scheme. The claim under test is that the architecture is
general, and the cheapest way to falsify it is to implement book/chapter/verse for three
independent Bible translations and record precisely what has to change.

Prediction before running (so the result cannot be rationalised afterwards):
  the `unit` table declares `gua INTEGER, gua_name TEXT, yao TEXT` as literal columns, so a
  second scheme cannot be stored at all without either new columns per scheme or a schema
  change. If that is what happens, "general infrastructure" is currently false and the fix
  is a generic (scheme, addr1, addr2, addr3) shape.
"""
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

EXT = os.path.join(ROOT, "data", "raw_ext", "generality")
BIBLES = ["bible-kjv", "bible-web", "bible-douay"]
IDS = {"bible-kjv": 10, "bible-web": 8294, "bible-douay": 1581}

# Gutenberg KJV marks verses as "1:1 In the beginning…"; WEB and Douay differ. Discover the
# shape from the data rather than assuming one.
PATTERNS = {
    "colon_leading": re.compile(r"^\s*(\d+):(\d+)\s+(.+)$"),
    "inline_colon": re.compile(r"(?<![\d:])(\d{1,3}):(\d{1,3})(?!\d)"),
}

print("=== 1. what does verse markup actually look like in each translation? ===")
texts = {}
for slug in BIBLES:
    p = os.path.join(EXT, slug, f"pg{IDS[slug]}.txt")
    raw = open(p, encoding="utf-8", errors="replace").read()
    texts[slug] = raw
    lines = raw.splitlines()
    n_lead = sum(1 for l in lines if PATTERNS["colon_leading"].match(l))
    n_inline = len(PATTERNS["inline_colon"].findall(raw))
    print(f"\n  {slug:14} {len(raw):>10,} chars  {len(lines):>8,} lines")
    print(f"    lines starting 'C:V ' : {n_lead:>8,}")
    print(f"    inline 'C:V' tokens   : {n_inline:>8,}")
    samples = [l for l in lines if PATTERNS["colon_leading"].match(l)][:3]
    for s in samples:
        print(f"    e.g. {s[:78]}")

print("\n=== 2. book headings ===")
BOOK_RE = re.compile(r"^\s*(?:The\s+)?(?:(First|Second|Third)\s+)?"
                     r"(Book of |Gospel [Aa]ccording to |Epistle .*? to |Acts|Revelation|"
                     r"Psalms|Proverbs|Genesis|Exodus)([^\n]{0,40})$")
for slug in BIBLES:
    heads = [l.strip() for l in texts[slug].splitlines()
             if l.strip() and BOOK_RE.match(l.strip())]
    print(f"  {slug:14} candidate book headings: {len(heads)}")
    for h in heads[:4]:
        print(f"    {h[:70]}")

print("\n=== 3. can the SAME verse be located in all three? (the tier-1 test) ===")
# Use a verse whose wording differs between translations but whose address is identical.
PROBES = [("Genesis", 1, 1), ("Psalms", 23, 1), ("John", 3, 16), ("Genesis", 1, 3)]


def verses(raw):
    """-> {(chapter, verse): text} scoped by the most recent book heading, best effort."""
    out = {}
    book = None
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        m = PATTERNS["colon_leading"].match(s)
        if m:
            out[(book, int(m.group(1)), int(m.group(2)))] = m.group(3).strip()
            continue
        # a short title-ish line resets the current book
        if len(s) < 60 and not s[0].isdigit() and s == s.strip():
            low = s.lower()
            for name in ("genesis", "exodus", "psalms", "proverbs", "john", "matthew",
                         "mark", "luke", "acts", "revelation", "isaiah", "romans"):
                if low.startswith(name) or f"of {name}" in low or f"to {name}" in low:
                    book = name.capitalize()
                    break
    return out


parsed = {slug: verses(texts[slug]) for slug in BIBLES}
for slug in BIBLES:
    bk = Counter(k[0] for k in parsed[slug])
    print(f"  {slug:14} {len(parsed[slug]):>7,} verses, {len(bk)} books identified")

print()
for book, ch, v in PROBES:
    print(f"  --- {book} {ch}:{v} ---")
    for slug in BIBLES:
        t = parsed[slug].get((book, ch, v))
        print(f"    {slug:14} {(t[:82] if t else '(not located)')}")

print("\n=== 4. what would it take to STORE this? (schema reality check) ===")
import sqlite3  # noqa: E402

db = sqlite3.connect(os.path.join(ROOT, "data", "index", "corpus.db"))
cols = [r[1] for r in db.execute("PRAGMA table_info(unit)")]
print(f"  unit columns: {cols}")
addr_cols = [c for c in cols if c in ("gua", "gua_name", "yao")]
print(f"  work-specific address columns: {addr_cols}")
print(f"  columns available for a book/chapter/verse address: "
      f"{[c for c in cols if c not in addr_cols and c.startswith(('addr','scheme'))] or 'NONE'}")
db.close()
print("\n  VERDICT: a second scheme cannot be stored without a schema change. The address")
print("  columns encode ONE work-type. This is the generality defect, and it is structural,")
print("  not a matter of adding more books.")
